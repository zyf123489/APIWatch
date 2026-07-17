# APIWatch

> 面向本地开发态的、多框架 / 未来多语言的 **API 调用观测工具**。接入一行探针，即可在本地看板上看到每个 API 的调用次数、耗时、错误率、最近请求与 trace 信息。

轻量版、本地开发态的 API Observability——**本地运行、零后端、多框架统一、一行接入**。当前版本为 **0.3.0 Preview / MVP3**：支持 Python ASGI（FastAPI / Litestar）、Flask、Django，并提供 VSCode 插件开发版入口。架构按「契约先行」设计，未来可平行扩展到更多语言。

---

## 特性

- **一行接入**：FastAPI/Litestar、Flask、Django 均可用最小改动接入，无需改动业务接口代码。
- **本地运行、零后端**：一个本地 collector（`127.0.0.1:8765`）+ SQLite，不依赖任何云服务。
- **不影响业务**：事件 fire-and-forget 异步上报，collector 不可用时静默丢弃，绝不阻塞或拖慢请求。
- **请求级观测**：method / path / route / 状态码 / 耗时 / 错误 / trace_id，聚合出调用次数、平均耗时、P95、错误率、慢接口与错误接口排行。
- **W3C Trace Context**：trace 标识采用标准 `traceparent`，可与 OpenTelemetry 生态衔接，为未来分布式串联铺路。
- **语言中立契约**：探针与 collector 之间只传标准化 JSON，未来加 Go / Node 探针时 collector 与看板一行不改。

---

## 与现有工具的差异化

| 工具 | 定位 | APIWatch 的不同 |
|---|---|---|
| **OpenTelemetry + Jaeger/Zipkin** | 功能强大的分布式 tracing | 接入重、需跑后端；APIWatch 本地零后端、一行接入、开箱即用 |
| **Datadog / New Relic / Sentry** | 云端、面向生产环境、收费 | APIWatch 本地、免费、面向**开发态** |
| **django-debug-toolbar / flask-debugtoolbar** | 单框架、单进程内嵌 | APIWatch **跨框架统一**、独立 collector、可聚合看板、未来跨语言 |

**空白点**：「本地运行 + 零后端 + 多框架统一 + 一行接入 + 开发态聚焦」这个组合目前没有主流工具正面覆盖。

---

## 架构

```text
业务应用(:8080) + Python探针  ──POST /events──▶  Collector(:8765)  ──▶  Dashboard(:8765/dashboard)
        │                    统一JSON契约         SQLite + 聚合            原生HTML/JS
        └─(可选B) mount_dashboard="/APIWatch" 把看板挂到 :8080/APIWatch
```

**唯一扩展契约**：探针与 collector 之间只传符合 [`spec/event.schema.json`](./spec/event.schema.json) 的 JSON，`POST /events`。任何语言只要产出该 JSON 即可接入——collector 与 dashboard 与语言无关。

---

## 安装

APIWatch 分为两个包：探针（接入你的业务应用）与 collector（本地采集与看板服务）。

```bash
# 探针包（接入业务项目；核心运行时零强依赖）
pip install -e probes/python

# collector 包（本地采集 + 看板服务）
pip install -e collector
```

> 探针包运行时零强依赖（上报走标准库）；collector 依赖 fastapi / uvicorn / pydantic。

按需安装被观测框架：

```bash
pip install -e "probes/python[flask]"
pip install -e "probes/python[django]"
pip install -e "probes/python[all]"
```

VSCode 插件开发版：

```bash
cd vscode-extension
npm install --cache .npm-cache
npm run compile
```

然后在 VSCode 中打开 `vscode-extension/`，按 F5 启动 Extension Development Host。

> Windows PowerShell 如遇到脚本执行策略限制，使用 `npm.cmd test` / `npm.cmd run compile`。

---

## 快速开始

### 1. 启动本地 collector

```bash
apiwatch start                 # 默认 127.0.0.1:8765
```

打开看板：<http://127.0.0.1:8765/dashboard>

常用维护命令：

```bash
apiwatch doctor                # 检查 collector 是否可访问
apiwatch clear                 # 清空全部事件数据
apiwatch clear --project demo  # 只清空指定 project
```

VSCode 命令面板也提供同等入口：

```text
APIWatch: Start Collector
APIWatch: Stop Collector
APIWatch: Open Dashboard
APIWatch: Show Integration Guide
APIWatch: Doctor
```

### 2. 在业务应用接入探针

FastAPI / Litestar（ASGI）：

```python
from fastapi import FastAPI
from apiwatch.integrations.asgi import ApiWatchASGIMiddleware

app = FastAPI()
app.add_middleware(ApiWatchASGIMiddleware, project="demo", framework="fastapi")

# Litestar 同理（同为 ASGI）：
# from litestar.middleware import DefineMiddleware
# middleware = [DefineMiddleware(ApiWatchASGIMiddleware)]
```

Flask：

```python
from flask import Flask
from apiwatch.integrations.flask import ApiWatchFlask

app = Flask(__name__)
ApiWatchFlask(app, project="demo")
```

Django：

```python
# settings.py
MIDDLEWARE = [
    "apiwatch.integrations.django.ApiWatchDjangoMiddleware",
    # ...
]

APIWATCH_PROJECT = "demo"
```

### 3. 正常使用你的项目，然后看看板

```bash
python examples/fastapi_demo.py           # 示例应用跑在 :8080
python examples/flask_demo.py             # Flask 示例应用跑在 :8081
python examples/django_demo.py            # Django 示例应用跑在 :8082
curl http://127.0.0.1:8080/api/users/1    # 正常
curl http://127.0.0.1:8080/api/slow       # 慢接口
curl http://127.0.0.1:8080/api/boom       # 故意报错
```

回到 <http://127.0.0.1:8765/dashboard>，即可看到请求记录、耗时、P95、错误率、慢接口 / 错误接口排行。看板支持 project/framework 筛选和清空数据；点击最近请求可查看单请求详情、错误信息与 trace 字段。

---

## 看板两种部署模式

| 模式 | 看板地址 | 说明 |
|---|---|---|
| **A（默认）** | `127.0.0.1:8765/dashboard` | 独立 collector 服务，与业务解耦，可同时观测多个项目；collector 崩了不影响业务 |
| **B（可选开关）** | `业务应用端口/APIWatch` | 一个端口全搞定，符合「在自己应用里看数据」的直觉 |

启用 B 模式：

```python
app.add_middleware(ApiWatchASGIMiddleware, mount_dashboard="/APIWatch")
# 之后在 http://127.0.0.1:8080/APIWatch 看到看板
```

---

## 配置

探针支持代码传参与环境变量（环境变量优先级低于显式传参、高于默认值）：

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `APIWATCH_COLLECTOR_URL` | `http://127.0.0.1:8765` | collector 基地址 |
| `APIWATCH_PROJECT` | `default` | 项目名，用于区分多项目 |
| `APIWATCH_ENABLED` | `true` | 是否启用采集（`0`/`false`/`no` 关闭） |

collector 端：`APIWATCH_DB` 指定 SQLite 路径（默认 `apiwatch.db`），或用 `apiwatch start --db <path>`。

Collector 查询接口支持按 project/framework 筛选：

```text
GET /summary?project=demo&framework=fastapi
GET /apis?project=demo
GET /requests?framework=flask
DELETE /events?project=demo
```

---

## 事件契约与多语言扩展

事件结构是**语言中立的一等公民**，定义在 [`spec/`](./spec/)：

- [`spec/SPEC.md`](./spec/SPEC.md)：契约规范（字段、`/events` 接口、trace 规则、版本演进）。
- [`spec/event.schema.json`](./spec/event.schema.json)：版本化 JSON Schema（当前 `1.0`）。

**扩展一门新语言 = 只需新写一个探针，让它产出符合契约的 JSON。** collector 和看板一行都不用改——这正是 `probes/` 按语言分层的原因。

---

## 目录结构

```text
apiwatch/
  spec/                     # 语言中立的事件契约（一等公民）
    SPEC.md
    event.schema.json
  probes/                   # 探针按语言分层，未来横向扩展
    python/                 # 首发：Python ASGI（FastAPI / Litestar）
      apiwatch/core/        #   event / trace / client / config
      apiwatch/integrations/#   asgi / flask / django
      tests/
  collector/                # 语言无关：FastAPI + SQLite + 聚合
    apiwatch_collector/
      app.py storage.py aggregate.py models.py cli.py
      dashboard/index.html  # 原生 HTML/JS 看板
    tests/
  examples/
    fastapi_demo.py         # 端到端验证示例
    flask_demo.py           # Flask 端到端验证示例
    django_demo.py          # Django 端到端验证示例
  vscode-extension/         # VSCode 插件（MVP3）
```

---

## 运行测试

```bash
pip install pytest httpx flask django
pytest probes/python/tests collector/tests --basetemp .pytest_tmp -p no:cacheprovider

cd vscode-extension
npm.cmd test
```

发布前完整验证：

```bash
python scripts/release_check.py
```

该脚本会依次运行 Python 测试、VSCode 插件编译/测试，并在隔离端口上启动 collector 与 FastAPI demo，验证探针到看板的端到端闭环。

VSCode 插件手动检查清单：

```text
1. 在 VSCode 中打开 vscode-extension/
2. 按 F5 启动 Extension Development Host
3. 执行 APIWatch: Start Collector
4. 执行 APIWatch: Doctor
5. 执行 APIWatch: Open Dashboard
6. 执行 APIWatch: Show Integration Guide
7. 执行 APIWatch: Stop Collector
```

---

