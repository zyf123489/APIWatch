# Changelog

## 0.3.0 - MVP3

- 新增 VSCode 插件工程：`vscode-extension/`。
- 新增命令：Start Collector、Stop Collector、Open Dashboard、Show Integration Guide、Doctor。
- 插件可启动/停止本扩展启动的 collector，并复用已运行的 collector。
- 插件可识别 FastAPI、Litestar、Flask、Django 项目并生成接入指引。
- 插件支持配置 collector host/port、Python executable、dashboard 打开方式。
- 新增 VSCode 插件 TypeScript 单元测试。

## 0.2.x - MVP2 稳定化

- 新增 `apiwatch doctor`，用于检查本地 collector 是否可访问。
- 新增 `apiwatch clear`，用于清空 collector 中的事件数据，支持 `--project`。
- 新增 `DELETE /events`，支持清空全部事件或指定 project 的事件。
- 新增 `/filters`，dashboard 可获取 project/framework 选项。
- `/summary`、`/apis`、`/requests` 支持 `project` 和 `framework` 查询参数。
- Dashboard 新增 project/framework 筛选、手动刷新和清空数据按钮。
- 新增 Django demo：`examples/django_demo.py`。

## 0.2.0 - MVP2

- 新增 Flask 集成 `ApiWatchFlask`。
- 新增 Django middleware `ApiWatchDjangoMiddleware`。
- 新增共享请求采集模块，统一 ASGI / Flask / Django 的事件构造。
- Dashboard 最近请求支持单请求详情。
- 探针包新增 optional extras：`flask`、`django`、`all`。

## 0.1.0 - MVP1

- 首版 Python ASGI 探针。
- 本地 collector、SQLite 存储、聚合 API 和原生 dashboard。
- 支持请求级 method/path/route/status/duration/error/trace 信息采集。
