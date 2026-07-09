"""Flask 集成。

用法：

    from apiwatch.integrations.flask import ApiWatchFlask

    app = Flask(__name__)
    ApiWatchFlask(app, project="demo")
"""

from __future__ import annotations

from typing import Optional

from ..core.capture import build_event, start_capture
from ..core.client import ReportClient
from ..core.config import ApiWatchConfig


class ApiWatchFlask:
    """通过 Flask 请求钩子采集请求级 API 调用事件。"""

    def __init__(
        self,
        app=None,
        config: Optional[ApiWatchConfig] = None,
        project: Optional[str] = None,
        collector_url: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        self.base_config = config or ApiWatchConfig()
        self.project = project
        self.collector_url = collector_url
        self.enabled = enabled
        if app is not None:
            self.init_app(app)

    def init_app(self, app) -> None:
        """注册 Flask before/after/teardown 钩子。"""
        from flask import got_request_exception

        config = self._build_config(app)
        client = ReportClient(config)
        app.extensions = getattr(app, "extensions", {})
        app.extensions["apiwatch"] = {"config": config, "client": client}

        @app.before_request
        def _apiwatch_before_request():
            from flask import g, request

            if not config.enabled:
                return None
            g.apiwatch_capture = start_capture(request.headers.get("traceparent"))
            g.apiwatch_reported = False
            return None

        def _apiwatch_exception(_, exception):
            from flask import g

            g.apiwatch_error = exception

        got_request_exception.connect(_apiwatch_exception, app, weak=False)

        @app.after_request
        def _apiwatch_after_request(response):
            from flask import g

            if config.enabled and not getattr(g, "apiwatch_reported", False):
                exc = getattr(g, "apiwatch_error", None)
                self._emit(
                    app,
                    response.status_code,
                    type(exc).__name__ if exc is not None else None,
                    str(exc) if exc is not None else None,
                )
                g.apiwatch_reported = True
            return response

        @app.teardown_request
        def _apiwatch_teardown_request(exc):
            from flask import g

            if (
                config.enabled
                and exc is not None
                and not getattr(g, "apiwatch_reported", False)
            ):
                self._emit(app, 500, type(exc).__name__, str(exc))
                g.apiwatch_reported = True

    def _build_config(self, app) -> ApiWatchConfig:
        project = self.project
        if project is None:
            project = app.config.get("APIWATCH_PROJECT")
        collector_url = self.collector_url
        if collector_url is None:
            collector_url = app.config.get("APIWATCH_COLLECTOR_URL")
        enabled = self.enabled
        if enabled is None:
            enabled = app.config.get("APIWATCH_ENABLED")
        return self.base_config.with_overrides(
            project=project,
            collector_url=collector_url,
            enabled=enabled,
            framework="flask",
        )

    @staticmethod
    def _extract_route() -> Optional[str]:
        try:
            from flask import request

            rule = getattr(request, "url_rule", None)
            route = getattr(rule, "rule", None)
            return route if isinstance(route, str) and route else None
        except Exception:
            return None

    def _emit(
        self,
        app,
        status_code: int,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        try:
            from flask import g, request

            capture = getattr(g, "apiwatch_capture", None)
            if capture is None:
                return
            state = app.extensions["apiwatch"]
            event = build_event(
                state["config"],
                capture,
                method=request.method,
                path=request.path,
                status_code=status_code,
                route=self._extract_route(),
                error_type=error_type,
                error_message=error_message,
            )
            state["client"].report(event)
        except Exception:
            pass
