# APIWatch 修复计划

> 适用版本：`0.3.0 Preview / MVP3`  
> 编写日期：2026-07-10  
> 状态：待实施  
> 范围：collector、Python 探针、Dashboard、VS Code 扩展、发布与测试流程

## 1. 文档目标

本文档把当前代码审查发现的问题转化为可执行的修复任务，并给出实现约束、回归测试和验收标准。修复工作的总体目标是：

1. 消除可执行脚本注入、未授权跨域访问和破坏性操作风险。
2. 保证事件写入、聚合结果及各框架探针采集语义正确。
3. 让 B 模式 Dashboard 和 VS Code Collector 管理达到可用状态。
4. 为数据库增长、版本演进和发布验证建立明确边界。
5. 所有修复都必须有失败路径测试，不能只覆盖正常请求。

本轮不以增加新功能为目标。除非修复需要，不应同时重构无关模块或改变公开 API。

## 2. 优先级定义

| 优先级 | 含义 | 发布要求 |
|---|---|---|
| P0 | 安全、数据一致性或核心功能不可用 | 修复前不应发布下一 Preview |
| P1 | 明确的采集、展示或进程管理错误 | 下一 Preview 必须完成 |
| P2 | 数据增长、资源生命周期、标准兼容和发布工程问题 | 稳定版前完成 |

## 3. 修复总表

| ID | 优先级 | 模块 | 问题 | 目标状态 |
|---|---:|---|---|---|
| WEB-01 | P0 | B 模式 Dashboard | 双花括号导致 CSS/JS 不可运行；修复后存在未转义数据 | 页面可运行，所有外部数据安全渲染 |
| SEC-01 | P0 | 主 Dashboard | `method` 可注入 HTML/脚本 | 不可信字段不再进入 HTML 属性或脚本上下文 |
| STO-01 | P0 | SQLite | 批量写入失败后可能部分提交 | 每个批次完全提交或完全回滚 |
| API-01 | P0 | Collector API | `EventIn` 未落实事件契约 | 非法事件在写库前被拒绝 |
| SEC-02 | P0 | Collector API | 任意 Origin 可读、写、删除且无鉴权 | 默认最小暴露，非回环绑定必须受保护 |
| EXT-01 | P1 | VS Code 扩展 | 启动假成功、未处理 spawn error、启停竞态 | 进程状态可验证且可恢复 |
| AGG-01 | P1 | 聚合 | 不同 method/project/framework 被错误合并 | API 身份维度完整且展示一致 |
| PROBE-01 | P1 | Django 探针 | 默认异常路径丢失异常详情 | 默认配置可记录异常类型和消息 |
| PROBE-02 | P1 | 三类探针 | 流式响应耗时、异常或状态不准确 | 以响应实际生命周期为采集边界 |
| CONF-01 | P1 | 探针配置 | 显式 URL 尾斜杠生成 `//events` | 所有配置入口统一规范化 URL |
| UI-01 | P1 | 主 Dashboard | 空结果残留、trace 详情错位、清理范围不一致 | 页面只展示当前筛选和当前请求的数据 |
| PERF-01 | P2 | Collector/SQLite | 无保留策略且周期性全表聚合 | 存储有界，查询成本可预测 |
| CLIENT-01 | P2 | ReportClient | 无 shutdown/flush，队列记账不完整 | 线程可关闭，丢弃行为可测试和观测 |
| TRACE-01 | P2 | Trace Context | 接受 W3C 非法 parent-id/version | 仅复用合法 trace context |
| REL-01 | P2 | 发布流程 | 固定端口、允许 skip、未验证发布物 | 在干净环境中验证真实安装产物 |

## 4. P0 修复

### WEB-01：修复 B 模式 Dashboard

涉及文件：

- [`probes/python/apiwatch/integrations/asgi.py`](probes/python/apiwatch/integrations/asgi.py)
- [`probes/python/tests/test_asgi.py`](probes/python/tests/test_asgi.py)

当前模板包含 `body{{...}}`、`function refresh(){{...}}`、`${{c[1]}}` 等原本用于字符串格式化转义的双花括号，但 `_serve_dashboard()` 只调用 `.replace()`。实际响应中的 JavaScript 无法通过语法解析。

修复要求：

1. 将模板恢复为合法 CSS 和 JavaScript，不要依赖容易混淆的二次字符串格式化。
2. `collector_url` 必须作为 JSON 字符串序列化后注入，不能直接拼入脚本字符串。
3. `route`、`path` 和任何 Collector 返回字段必须通过 `textContent`/DOM API 渲染；不得直接进入 `innerHTML`。
4. 优先抽取主 Dashboard 已验证的安全渲染逻辑，减少维护两套模板。若暂时保留轻量页面，也必须共享转义和格式化测试用例。
5. B 模式功能修复和 XSS 修复必须在同一个变更中完成，禁止先恢复脚本执行、后补转义。

验收标准：

- `GET /APIWatch` 返回的脚本可通过 `node --check` 或等价语法检查。
- 页面能成功读取 `/summary` 和 `/apis` 并定时刷新。
- `route/path` 为 `<img src=x onerror=...>` 时只显示字面文本，不创建元素、不执行事件处理器。
- `collector_url` 含引号、反斜杠或换行时不会破坏脚本结构。

### SEC-01：消除主 Dashboard 存储型 XSS

涉及文件：

- [`collector/apiwatch_collector/dashboard/index.html`](collector/apiwatch_collector/dashboard/index.html)
- [`collector/tests/test_api.py`](collector/tests/test_api.py)

修复要求：

1. `methodClass()` 只能返回固定 CSS class，例如 `m-get`、`m-post`、`m-put`、`m-patch`、`m-delete`、`m-other`。
2. 禁止把 API 返回值直接拼入 HTML 属性。优先使用 `document.createElement()`、`classList.add()` 和 `textContent`。
3. 对 `project/framework/method/path/route/error_message/trace` 建立统一的不可信数据规则。
4. 在页面完全移除内联脚本或引入 nonce/hash 后增加 CSP。CSP 是第二道防线，不能替代正确编码。

验收标准：

- 使用 `method='x\"><img src=x onerror=alert(1)>'` 写入事件后，看板无脚本执行且 DOM 中没有注入的 `img`。
- 同一组安全测试同时覆盖列表、详情、筛选项和排行。
- 正常 HTTP method 的颜色样式不回退。

### STO-01：保证批量写入原子性

涉及文件：

- [`collector/apiwatch_collector/storage.py`](collector/apiwatch_collector/storage.py)
- [`collector/tests/test_storage.py`](collector/tests/test_storage.py)
- [`collector/tests/test_api.py`](collector/tests/test_api.py)

推荐实现：在同一个锁和 SQLite transaction context 内完成整个 `executemany()`；任意异常都必须 rollback 后重新抛出。不要依赖后续请求隐式结束前一个事务。

```python
with self._lock:
    with self._conn:
        self._conn.executemany(sql, rows)
```

修复要求：

1. 进入事务前完成能够完成的事件预校验和行转换。
2. 写入失败后连接仍可继续执行查询和下一次写入。
3. API 返回的 `accepted` 必须只表示已经提交的条数。
4. 明确单批最大条数，建议初始上限为 1000；超限请求直接拒绝，不做部分截断。

验收标准：

- 第二条记录绑定失败时，第一条也不可见，下一次正常 commit 后仍不可见。
- 批次成功时所有记录一次提交。
- 并发正常写入和失败写入不会使连接长期停留在 transaction 中。

### API-01：落实事件契约和请求边界

涉及文件：

- [`spec/event.schema.json`](spec/event.schema.json)
- [`spec/SPEC.md`](spec/SPEC.md)
- [`collector/apiwatch_collector/models.py`](collector/apiwatch_collector/models.py)
- [`collector/apiwatch_collector/app.py`](collector/apiwatch_collector/app.py)

必须校验：

| 字段 | 规则 |
|---|---|
| `schema_version` | 当前仅接受明确支持的版本；至少拒绝非 `1.x` major |
| `project/framework` | 非空，设置合理最大长度 |
| `method` | 非空且符合 HTTP token 规则，设置最大长度 |
| `path/route` | path 非空；二者均设置最大长度 |
| `status_code` | `100..599` |
| `duration_ms` | 有限数值且 `>= 0` |
| `trace_id/span_id` | 小写 hex、正确长度且不得全零 |
| `traceparent` | W3C 格式合法，且内部 ID 与独立字段一致 |
| `timestamp` | 可解析、包含时区的 ISO 8601 |
| `error_type/error_message` | 可空，但必须设置长度上限 |

版本兼容需要先做出明确选择。当前 JSON Schema 的 `additionalProperties: false` 与 SPEC 中“旧 Collector 接受未来 minor 字段”的承诺冲突。推荐在 `1.0` 阶段先严格拒绝未知字段；在设计 `1.1` 前，通过显式 `attributes` 扩展对象或调整规范解决向前兼容，不能让运行时和文档继续各自解释。

同时增加：

1. HTTP body 大小上限，避免在 Pydantic 校验前加载无限数组。
2. 单批事件条数上限。
3. 明确的 4xx 错误响应，不写入任何数据。
4. Pydantic v1/v2 共用的校验实现和测试，避免只在当前环境可用。

验收标准：

- JSON Schema 中每个边界至少有一个 API 测试。
- `NaN`、`Infinity`、`1e309`、超大整数、空字符串、非法 trace 和未知字段均被拒绝。
- 所有 4xx 请求前后数据库行数保持不变。

### SEC-02：收紧 Collector 暴露面

涉及文件：

- [`collector/apiwatch_collector/app.py`](collector/apiwatch_collector/app.py)
- [`collector/apiwatch_collector/cli.py`](collector/apiwatch_collector/cli.py)
- Python 探针及 VS Code 配置

推荐策略：

1. A 模式默认不启用跨域访问，Dashboard 与 API 使用同源请求。
2. B 模式要求显式配置允许的业务应用 Origin，不允许 `*`。
3. 非回环地址启动时必须要求访问 token；token 至少保护事件写入、请求详情和删除接口。
4. `DELETE /events` 增加更强保护，可使用 bearer token 加确认 header，避免仅凭跨域请求触发。
5. 校验 `Host`，防止 DNS rebinding 绕过“仅本地”假设。
6. 限制和可选脱敏 `error_message`，文档明确其可能包含敏感数据。
7. 增加最小 `/health` 接口，供 VS Code 做身份和就绪检查；该接口不返回观测数据。

验收标准：

- 未授权 Origin 的预检、POST、GET、DELETE 均失败。
- 合法 B 模式 Origin 可以正常读数。
- `--host 0.0.0.0` 未配置 token 时拒绝启动或输出明确错误。
- Dashboard 和探针在启用 token 后仍能完成端到端闭环。

## 5. P1 修复

### EXT-01：重做 CollectorManager 状态管理

涉及文件：

- [`vscode-extension/src/collector.ts`](vscode-extension/src/collector.ts)
- [`vscode-extension/src/extension.ts`](vscode-extension/src/extension.ts)
- 新增 CollectorManager 测试

修复要求：

1. 使用 `stopped -> starting -> running -> stopping` 状态机，并串行化 start/stop 操作。
2. 注册 `error`、`exit`、`stdout`、`stderr` 监听后再暴露启动结果。
3. spawn 后轮询 `/health`，只有确认服务身份和版本后才返回 `started`。
4. 启动超时、模块缺失、端口占用和进程提前退出必须返回明确失败，不得显示“started”。
5. exit 回调捕获局部 `child`，仅当 `this.process === child` 时清空当前句柄。
6. Stop 必须等待目标进程退出或超时；Windows 下验证不会留下孤儿进程。
7. 数据库路径放入 `ExtensionContext.storageUri` 或明确的工作区存储目录，并通过 `--db` 传给 CLI，不能依赖 `process.cwd()`。

验收标准：

- 不存在的 Python、未安装模块、占用端口均有自动测试。
- 两次并发 Start 最多产生一个子进程。
- Stop 后立即 Start 不会丢失新进程句柄。
- 扩展 deactivate 后由它启动的 Collector 已退出。

### AGG-01：修正 API 聚合身份

涉及文件：

- [`collector/apiwatch_collector/storage.py`](collector/apiwatch_collector/storage.py)
- [`collector/apiwatch_collector/aggregate.py`](collector/apiwatch_collector/aggregate.py)
- [`collector/apiwatch_collector/models.py`](collector/apiwatch_collector/models.py)
- Dashboard API 表格

API 的最小身份应为：

```text
(project, framework, method, route-or-path)
```

即使查询参数已经限定 project/framework，返回对象仍应包含这些维度，避免调用方依赖隐式上下文。Dashboard 至少显示 method + route；默认“全部”视图不能合并不同项目的同名接口。

验收标准：

- 同一路由的 GET 200 和 DELETE 500 分成两行，错误率互不影响。
- 两个项目的 `/health` 分开统计。
- route 缺失时仍以当前项目、框架、method 和 path 正确分组。

### PROBE-01：捕获 Django 默认异常路径

涉及文件：

- [`probes/python/apiwatch/integrations/django.py`](probes/python/apiwatch/integrations/django.py)
- [`probes/python/tests/test_django.py`](probes/python/tests/test_django.py)

不要依赖外层 `try/except` 捕获 view 异常。应通过 Django 的 exception middleware hook 在异常转换为 500 Response 前把异常保存到 request，再由统一的 emit 路径上报，并保证只上报一次。

验收标准：

- `DEBUG_PROPAGATE_EXCEPTIONS=False` 和 `DEBUG=False` 下，未处理异常仍记录类型和消息。
- 自定义异常处理器返回非 500 时，状态码取实际响应，是否标记 error 必须有明确规则和测试。
- 中间件顺序变化不会产生重复事件。

### PROBE-02：统一流式响应采集语义

涉及文件：

- [`probes/python/apiwatch/integrations/asgi.py`](probes/python/apiwatch/integrations/asgi.py)
- [`probes/python/apiwatch/integrations/flask.py`](probes/python/apiwatch/integrations/flask.py)
- [`probes/python/apiwatch/integrations/django.py`](probes/python/apiwatch/integrations/django.py)

统一约定：`duration_ms` 从请求进入探针开始，到响应 iterable/ASGI body 完成或失败为止。

实现要求：

1. ASGI 记录 `response_started`。异常发生在响应开始前才使用 500；已经发送 `http.response.start` 后必须保留实际状态，同时记录异常。
2. Flask 包装 WSGI response iterable，在完成、异常和 close 路径中只 emit 一次。
3. Django 分别包装同步和异步 `streaming_content`，非流式响应沿用普通路径。
4. 包装器必须保留原始 close 行为，不能改变 chunk 顺序或吞掉异常。

验收标准：

- 150ms 后才产出首块的流式响应，记录耗时不得接近 0ms。
- 先发送 200/204 后迭代失败，事件保留 200/204 并包含异常。
- 客户端中断、空流、同步流和异步流均有测试。

### CONF-01：统一 URL 规范化

涉及文件：

- [`probes/python/apiwatch/core/config.py`](probes/python/apiwatch/core/config.py)
- [`probes/python/apiwatch/core/client.py`](probes/python/apiwatch/core/client.py)

在 `ApiWatchConfig` 的统一初始化路径中规范化 URL，而不是只在环境变量 default factory 中处理。应验证 scheme/host，并使用结构化 URL 拼接生成 `/events`。

验收标准：

- 环境变量、构造函数、ASGI 参数、Flask config、Django settings 的有/无尾斜杠结果相同。
- 非 HTTP(S)、缺少 host 和包含 query/fragment 的基地址按明确规则拒绝。
- ReportClient 测试确认实际请求路径为 `/events`。

### UI-01：修复 Dashboard 状态一致性

涉及文件：

- [`collector/apiwatch_collector/dashboard/index.html`](collector/apiwatch_collector/dashboard/index.html)
- [`collector/apiwatch_collector/app.py`](collector/apiwatch_collector/app.py)
- [`collector/apiwatch_collector/storage.py`](collector/apiwatch_collector/storage.py)

修复要求：

1. `apis=[]` 时同时清空主表、慢接口和错误接口排行。
2. 为 refresh 增加 generation ID 或 AbortController，旧筛选请求不能覆盖新结果。
3. 任一接口失败时显示明确的局部错误状态，不保留无法识别的新旧混合快照。
4. trace 详情按当前行的 `id` 或 `span_id` 定位，不得固定显示 `spans[0]`。
5. 清理范围必须与当前筛选一致：后端支持 project + framework，或 UI 明确禁用不支持的组合并显示精确删除范围。
6. 删除当前 project 后不能静默切到“全部”并立即展示其他项目数据。

验收标准：

- 从有数据筛选切到空结果时三个区域全部为空。
- 人为制造乱序响应时，只呈现最后一次筛选。
- 同一 trace 有多个事件时，点击每行显示对应事件。
- `project=A, framework=flask` 的清理不会删除 A 的 Django 数据。

## 6. P2 修复

### PERF-01：让存储和聚合成本有界

推荐初始策略：默认保留最近 7 天且最多 50,000 条事件，两项均可配置。最终数值应通过性能测试确定，并在 README 中公开。

修复要求：

1. 增加 `(project, framework)`、时间及常用组合索引。
2. summary 的 count/sum/max/error_count 尽量下推 SQLite。
3. P95 采用明确算法；如果继续在 Python 计算，只读取受时间窗口或数量上限约束的数据。
4. 每次 ingest 后低频执行保留策略，避免每条事件都做大 DELETE。
5. Dashboard 一次刷新共享同一统计快照，避免 `/summary`、`/apis` 重复全表读取。
6. 增加 SQLite `busy_timeout`；是否启用 WAL 需通过 Windows 和多线程测试决定。
7. `clear` 默认只删除数据；另提供显式 compact/vacuum 命令并提示其阻塞成本。

性能验收基线：

- 50,000 条事件下连续刷新不会产生随请求次数持续增长的内存。
- 聚合期间 ingest 延迟有明确上限，不因全表 fetch 长时间占锁。
- 保留策略运行后行数回到配置上限。

### CLIENT-01：补齐 ReportClient 生命周期

修复要求：

1. 增加幂等 `close(flush_timeout=...)`，用 sentinel 结束 worker。
2. 框架关闭钩子和测试显式调用 close；daemon 只能作为最后兜底。
3. 队列丢弃旧事件时补齐 `task_done()`，保持 unfinished task 计数正确。
4. 明确队列满时的并发策略，保证最新事件不会因竞争被意外丢弃。
5. 增加 `sent/dropped/failed` 内部计数或诊断接口，但不得让上报失败影响业务请求。

### TRACE-01：严格实现 W3C Trace Context

修复要求：

1. 拒绝全零 trace-id 和 parent-id。
2. 拒绝保留 version `ff`。
3. 对 version `00` 实施正确长度和格式规则；未来版本按 W3C 的扩展规则处理。
4. 明确是否继承入站 sampled flag，不再无说明地固定改为 `01`。
5. Collector 同时校验 `traceparent` 与独立 `trace_id/span_id` 一致。

### REL-01：建立可信发布门禁

涉及文件：

- [`scripts/release_check.py`](scripts/release_check.py)
- 两个 `pyproject.toml`
- `vscode-extension/package.json`
- 新增 CI workflow

修复要求：

1. 使用系统分配的空闲端口，并确认 `server.started`；线程异常必须传播到主流程。
2. 发布环境安装探针的 `all` extra，Flask/Django/Litestar 缺失时直接失败，不允许静默 skip。
3. 构建 wheel/sdist，在干净虚拟环境安装后再运行 smoke/e2e。
4. 验证 `apiwatch` CLI entry point、Dashboard package data、版本号和 metadata。
5. 增加 Python 3.8/3.10/当前版本、Pydantic v1/v2 和最低依赖版本矩阵。
6. VS Code 扩展至少增加 TypeScript 单测和真实 Extension Host smoke test，覆盖声明的最低 VS Code 版本。
7. 增加正式 `LICENSE` 文件，并让两个包的 metadata 与仓库许可证一致。

## 7. 数据库迁移与兼容策略

修复校验后，已有 SQLite 文件中可能仍包含非法状态码、负数或非有限耗时、错误 trace 等历史数据，不能假设新模型会自动修复旧行。

建议：

1. 使用 `PRAGMA user_version` 管理数据库 schema 版本。
2. 首次升级前创建同目录备份，迁移失败不得覆盖原库。
3. 增加 project/framework 复合索引和其他 schema 变更时使用单事务迁移。
4. 扫描历史非法行并移动到 `events_rejected`，记录原因；Preview 阶段也可选择备份后删除，但必须在 changelog 中说明。
5. 聚合查询只读取通过约束的数据，防止旧行继续输出负数或 `null` 指标。
6. `apiwatch doctor` 输出数据库版本、非法行数和是否需要 compact。

## 8. 回归测试矩阵

| 层级 | 必测场景 |
|---|---|
| 模型/API | 每个 schema 边界、未知版本、未知字段、body/batch 上限 |
| 事务 | 中途绑定失败、磁盘/锁异常模拟、失败后连接复用 |
| 安全 | 主/B Dashboard XSS、CORS allow/deny、token、Host 校验、DELETE 授权 |
| ASGI | 正常、异常前/后 response.start、同步/异步流、客户端中断、B 模式 |
| Flask | 正常、异常处理器、流式完成/失败、close |
| Django | 默认异常转换、自定义异常处理、同步/异步 StreamingHttpResponse |
| 聚合 | method/project/framework 隔离、route fallback、空集、P95 边界 |
| Dashboard | 空筛选、乱序响应、多 span、局部 API 失败、精确清理范围 |
| ReportClient | 启停、flush 超时、队列满、网络超时、并发 report |
| VS Code | spawn ENOENT、模块缺失、端口占用、并发 Start、快速重启、deactivate |
| 发布物 | wheel/sdist、CLI、package data、版本、最低版本矩阵 |
| 性能 | 50k 事件聚合、并发 ingest、保留清理、内存和锁等待 |

测试要求：

- 发布检查中不得存在意外 skip。
- 新增失败路径测试应先在旧实现上失败，再随修复转绿。
- 安全测试必须检查 DOM 结果或真实浏览器行为，不能只搜索 HTML 字符串。
- 涉及线程、进程和网络的测试必须有超时与清理逻辑，不能留下后台进程或临时目录。

## 9. 推荐实施顺序

### 阶段 A：阻断安全与数据一致性风险

- [ ] WEB-01：B 模式可运行且安全渲染
- [ ] SEC-01：主 Dashboard XSS
- [ ] STO-01：原子批量写入
- [ ] API-01：事件校验和请求上限
- [ ] SEC-02：CORS、Host 和授权策略

完成阶段 A 后发布 `0.3.1` 安全修复版，并在 changelog 中明确兼容性变化。

### 阶段 B：修正用户可见行为

- [ ] EXT-01：VS Code 进程状态机
- [ ] AGG-01：聚合身份
- [ ] PROBE-01：Django 默认异常
- [ ] PROBE-02：流式响应
- [ ] CONF-01：URL 规范化
- [ ] UI-01：Dashboard 状态一致性

完成阶段 B 后再增加框架或语言探针，避免把错误契约扩散到更多实现。

### 阶段 C：稳定性与发布工程

- [ ] PERF-01：有界存储和聚合
- [ ] CLIENT-01：ReportClient 生命周期
- [ ] TRACE-01：W3C trace 校验
- [ ] REL-01：发布物、版本矩阵和 CI
- [ ] 数据库迁移、备份和 doctor 检查

## 10. 整体验收标准

只有同时满足以下条件，修复计划才视为完成：

1. P0/P1 条目全部关闭，并有对应自动化回归测试。
2. 主 Dashboard 与 B 模式对所有事件字符串都采用安全渲染。
3. 非法事件不会写库，失败批次不会留下任何记录。
4. 三类探针对普通、异常和流式响应使用一致且已文档化的语义。
5. VS Code 不会把启动失败报告为成功，也不会遗留无法管理的 Collector。
6. 默认数据规模有上限，聚合不会持续全表读取无限增长的数据。
7. 发布检查验证真实安装产物，在支持矩阵中无意外 skip。
8. README、SPEC、CHANGELOG、CLI 帮助和配置项与最终行为一致。

