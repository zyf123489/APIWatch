# Python API 本地观测插件想法笔记

## 1. 一句话定位

做一个面向 Python Web 开发者的本地 API 调用观测插件：安装后可以监控当前本地项目的 API 调用情况，并通过本地看板展示接口耗时、调用次数、错误率、最近请求和 trace 信息。

可以理解为：轻量版、本地开发态的 API Observability 工具，先支持 Python Web 框架，后续再扩展到更多语言或平台。

## 2. 核心想法

开发者在本地开发 Django、Flask、FastAPI、Litestar 项目时，经常需要知道：

- 哪些 API 被调用了
- 每个 API 调用了多少次
- 平均耗时、P95 耗时是多少
- 哪些接口慢
- 哪些接口报错
- 最近一次错误是什么
- 某次请求对应的 trace id 是什么
- 前端一次操作如何关联到后端 API 请求

这个插件希望做到：用户安装插件或接入一行 middleware 后，就能在本地 dashboard 里看到这些信息。

## 3. 目标支持框架

第一阶段聚焦 Python Web 框架：

- FastAPI
- Litestar
- Flask
- Django

推荐实现顺序：

1. FastAPI / Litestar：同属 ASGI，middleware 逻辑可复用
2. Flask：通过 request hooks 采集
3. Django：通过 Django middleware 采集
4. VSCode 插件：在底层能力稳定后包装成插件体验

## 4. 产品形态

整体产品可以拆成四层：

### 4.1 Python 探针包

负责接入不同 Python Web 框架，采集请求信息。

可能的包结构：

```text
apiwatch/
  core/
    event.py        # 统一 API 调用事件模型
    trace.py        # trace_id/span_id/traceparent 生成
    client.py       # 上报事件到本地 collector
    config.py       # 配置
  integrations/
    asgi.py         # FastAPI / Litestar
    flask.py        # Flask 集成
    django.py       # Django middleware
```

### 4.2 本地 Collector

本地启动一个轻量服务，例如：

```text
http://127.0.0.1:8765
```

负责：

- 接收探针上报的 API 调用事件
- 写入本地 SQLite 或内存存储
- 聚合接口指标
- 提供 dashboard 查询接口

示例接口：

```text
POST /events
GET  /summary
GET  /apis
GET  /requests
GET  /requests/{trace_id}
```

### 4.3 Dashboard 看板

本地看板用于展示 API 调用情况：

- API 列表
- 总请求数
- 平均耗时
- P95 耗时
- 错误率
- 慢接口排行
- 错误接口排行
- 最近请求列表
- 单次请求详情
- trace_id / span_id / traceparent

可以先做成独立本地 Web 页面：

```text
http://127.0.0.1:8765/dashboard
```

后续再嵌入 VSCode Webview。

### 4.4 VSCode 插件

VSCode 插件第一版不必做复杂自动注入，先做轻量入口：

- 检测当前项目使用的 Python Web 框架
- 启动 / 停止本地 collector
- 打开 dashboard
- 根据框架生成接入指引
- 展示当前项目的 API 观测状态

命令示例：

```text
ApiWatch: Start Collector
ApiWatch: Stop Collector
ApiWatch: Open Dashboard
ApiWatch: Show Integration Guide
```

## 5. 统一事件模型

探针采集后统一上报一种事件结构。

示例：

```json
{
  "project": "my-service",
  "framework": "fastapi",
  "method": "GET",
  "path": "/api/users/1",
  "route": "/api/users/{id}",
  "status_code": 200,
  "duration_ms": 18.42,
  "trace_id": "0123456789abcdef0123456789abcdef",
  "span_id": "0123456789abcdef",
  "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
  "timestamp": "2026-07-08T12:00:00+08:00",
  "error_type": null,
  "error_message": null
}
```

第一版不追求复杂分布式 tracing，先把请求级 API 调用采集稳定。

## 6. 各框架接入方式

### 6.1 FastAPI

```python
from apiwatch.integrations.asgi import ApiWatchASGIMiddleware

app.add_middleware(ApiWatchASGIMiddleware)
```

### 6.2 Litestar

```python
from litestar.middleware import DefineMiddleware
from apiwatch.integrations.asgi import ApiWatchASGIMiddleware

middleware = [DefineMiddleware(ApiWatchASGIMiddleware)]
```

### 6.3 Flask

```python
from apiwatch.integrations.flask import FlaskApiWatch

observer = FlaskApiWatch(app)
```

### 6.4 Django

```python
MIDDLEWARE = [
    "apiwatch.integrations.django.ApiWatchMiddleware",
    ...
]
```

## 7. MVP 路线

### MVP 1：最小可运行闭环

目标：先不做 VSCode 插件，只做命令行 + 本地 dashboard。

包含：

- Python 探针包
- ASGI middleware
- 支持 FastAPI / Litestar
- 本地 collector
- SQLite 存储
- Web dashboard
- 采集 method、path、status_code、duration_ms、error、trace_id

这个版本可以最快验证想法。

### MVP 2：补齐 Python 主流框架

包含：

- Flask 集成
- Django middleware
- 框架识别字段
- route pattern 提取
- 最近请求详情页

### MVP 3：VSCode 插件化

包含：

- VSCode 命令面板入口
- 自动识别项目框架
- 启动本地 collector
- 打开 dashboard
- 展示接入代码
- 可选 Webview 内嵌看板

### MVP 4：增强诊断能力

包含：

- 慢接口检测
- 错误接口排行
- P95/P99 指标
- traceparent 响应头
- 请求详情瀑布图
- 简单诊断建议

## 8. 技术难点与规避策略

### 难点 1：多框架生命周期不同

规避策略：统一事件模型，不强行统一框架内部实现。每个框架只负责把自己的请求生命周期转换成统一事件。

### 难点 2：自动修改用户代码风险高

规避策略：第一版不自动注入，只展示接入代码。后续再做可确认的一键修改。

### 难点 3：性能开销

规避策略：本地开发态优先，事件上报异步化，collector 不可用时不影响业务请求。

### 难点 4：route pattern 获取不一致

规避策略：第一版 path 必采，route 尽力采集。采不到 route 时用 path 兜底。

### 难点 5：看板复杂度膨胀

规避策略：第一版只做 API 列表、指标卡、最近请求、错误排行。不要一开始做完整 APM。

## 9. 可以包装的软著方向

可选名称：

- Python Web API 本地调用观测插件系统
- 开发态接口链路追踪与性能分析软件
- 多框架 API 调用遥测采集与可视化系统
- 本地 API 监控与诊断看板软件
- Python Web 服务接口性能监测插件软件

功能描述可以写：

> 本软件面向 Python Web 开发环境，支持 Django、Flask、FastAPI、Litestar 等框架，通过统一请求探针采集 API 调用数据，生成链路标识，记录状态码、耗时、错误、调用频次等指标，并通过本地采集服务和可视化看板提供接口性能分析、错误定位和开发态诊断能力。

## 10. 推荐最终方向

建议先做：

```text
Python API 本地观测插件系统
```

第一版重点不是“大而全监控平台”，而是：

- 本地运行
- 接入简单
- Python 多框架支持
- API 调用可视化
- 错误和慢接口可定位
- 能与 traceparent / OpenTelemetry 思路衔接

这条路线工程量可控，产品形态清楚，也适合作为软著主题。
