"""ASGI 中间件：FastAPI / Litestar 通用。

纯 ASGI 实现，只依赖 ASGI 协议（不 import fastapi / starlette / litestar 的具体类），
因此同一份中间件可用于任何 ASGI 框架。采集请求级事件（粒度 1）并 fire-and-forget 上报。

用法：

    # FastAPI
    from apiwatch.integrations.asgi import ApiWatchASGIMiddleware
    app.add_middleware(ApiWatchASGIMiddleware)

    # Litestar
    from litestar.middleware import DefineMiddleware
    middleware = [DefineMiddleware(ApiWatchASGIMiddleware)]

可选 B 模式：把看板挂到业务应用端口下（默认走独立 collector 服务）：

    app.add_middleware(ApiWatchASGIMiddleware, mount_dashboard="/APIWatch")
"""

from __future__ import annotations

from typing import Optional

from ..core.client import ReportClient
from ..core.config import ApiWatchConfig
from ..core.capture import build_event, start_capture

# B 模式看板外壳：自包含的轻量 HTML，JS 通过 API_BASE 指向独立 collector 取数。
# 完整看板仍以 collector 的 dashboard/index.html 为准，这里只是便捷入口。
_MOUNT_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>APIWatch</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:24px;color:#1f2933;background:#f5f7fa}}
 h1{{font-size:20px}} .cards{{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0}}
 .card{{background:#fff;border:1px solid #e4e7eb;border-radius:10px;padding:16px 20px;min-width:140px}}
 .card .v{{font-size:26px;font-weight:600}} .card .k{{color:#7b8794;font-size:12px;margin-top:4px}}
 table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden}}
 th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid #eef1f4;font-size:13px}}
 th{{background:#f0f4f8;color:#52606d}} .err{{color:#cf1124}}
</style>
</head>
<body>
<h1>APIWatch · 本地 API 观测</h1>
<div class="cards" id="cards"></div>
<h3>接口</h3>
<table id="apis"><thead><tr><th>Route</th><th>次数</th><th>平均(ms)</th><th>P95(ms)</th><th>错误率</th></tr></thead><tbody></tbody></table>
<script>
const API_BASE = "__API_BASE__";
async function j(p){{try{{const r=await fetch(API_BASE+p);return await r.json()}}catch(e){{return null}}}}
async function refresh(){{
 const s=await j("/summary");
 if(s){{document.getElementById("cards").innerHTML=[
   ["总请求",s.total_requests],["平均耗时",(s.avg_duration_ms||0).toFixed(1)+"ms"],
   ["P95",(s.p95_duration_ms||0).toFixed(1)+"ms"],["错误率",((s.error_rate||0)*100).toFixed(1)+"%"]
 ].map(c=>`<div class="card"><div class="v">${{c[1]}}</div><div class="k">${{c[0]}}</div></div>`).join("");}}
 const a=await j("/apis");
 if(a&&a.apis){{document.querySelector("#apis tbody").innerHTML=a.apis.map(x=>
   `<tr><td>${{x.route||x.path}}</td><td>${{x.count}}</td><td>${{(x.avg_ms||0).toFixed(1)}}</td><td>${{(x.p95_ms||0).toFixed(1)}}</td><td class="${{x.error_rate>0?'err':''}}">${{((x.error_rate||0)*100).toFixed(1)}}%</td></tr>`
 ).join("");}}
}}
refresh();setInterval(refresh,3000);
</script>
</body>
</html>"""


def _extract_route(scope: dict) -> Optional[str]:
    """尽力从 scope 提取路由模板（占位形式）。取不到返回 None，由上层用 path 兜底。

    Starlette / FastAPI 在路由匹配后会把 route 对象写入同一个 scope dict，
    因此需在下游 app 调用之后再读取。Litestar 的键名不同，这里做多路尝试。
    """
    try:
        route = scope.get("route")
        if route is not None:
            path_format = getattr(route, "path_format", None) or getattr(
                route, "path", None
            )
            if isinstance(path_format, str) and path_format:
                return path_format
        # Litestar 风格兜底
        handler = scope.get("route_handler")
        if handler is not None:
            paths = getattr(handler, "paths", None)
            if paths:
                first = next(iter(paths))
                if isinstance(first, str) and first:
                    return first
    except Exception:
        return None
    return None


class ApiWatchASGIMiddleware:
    """采集 ASGI 请求级 API 调用事件的中间件。"""

    def __init__(
        self,
        app,
        config: Optional[ApiWatchConfig] = None,
        mount_dashboard: Optional[str] = None,
        project: Optional[str] = None,
        collector_url: Optional[str] = None,
        framework: str = "asgi",
    ) -> None:
        self.app = app
        base = config or ApiWatchConfig()
        self.config = base.with_overrides(
            project=project, collector_url=collector_url, framework=framework
        )
        self.mount_dashboard = mount_dashboard.rstrip("/") if mount_dashboard else None
        self._client = ReportClient(self.config)

    async def __call__(self, scope, receive, send):
        # 仅处理 HTTP，其余（websocket / lifespan）直接透传
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # B 模式：命中挂载前缀时，直接返回看板外壳，不进入业务
        if self.mount_dashboard and (
            path == self.mount_dashboard or path.startswith(self.mount_dashboard + "/")
        ):
            await self._serve_dashboard(send)
            return

        method = scope.get("method", "GET")
        # 生成 / 复用 trace 标识
        inbound = self._inbound_traceparent(scope)
        capture = start_capture(inbound)

        status_holder = {"status": 500}

        async def wrapped_send(message):
            if message.get("type") == "http.response.start":
                status_holder["status"] = message.get("status", 200)
            await send(message)

        error_type: Optional[str] = None
        error_message: Optional[str] = None

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception as exc:  # noqa: BLE001 — 采集后原样抛出，不吞异常
            error_type = type(exc).__name__
            error_message = str(exc)
            status_holder["status"] = 500
            self._emit(
                scope, method, path, status_holder["status"], capture,
                error_type, error_message,
            )
            raise
        else:
            self._emit(
                scope, method, path, status_holder["status"], capture, None, None,
            )

    def _emit(
        self, scope, method, path, status_code, capture, error_type, error_message,
    ) -> None:
        """组装事件并交给 fire-and-forget 客户端上报。任何异常都不得影响业务。"""
        try:
            route = _extract_route(scope)  # 路由匹配后 scope 已含 route，此处读取
            event = build_event(
                self.config,
                capture,
                method=method,
                path=path,
                status_code=status_code,
                route=route,
                error_type=error_type,
                error_message=error_message,
            )
            self._client.report(event)
        except Exception:
            pass

    @staticmethod
    def _inbound_traceparent(scope) -> Optional[str]:
        """从 ASGI headers 中取入站 traceparent（若有）。"""
        try:
            for name, value in scope.get("headers", []):
                if name == b"traceparent":
                    return value.decode("latin-1")
        except Exception:
            return None
        return None

    async def _serve_dashboard(self, send) -> None:
        html = _MOUNT_DASHBOARD_HTML.replace("__API_BASE__", self.config.collector_url)
        body = html.encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/html; charset=utf-8")],
        })
        await send({"type": "http.response.body", "body": body})
