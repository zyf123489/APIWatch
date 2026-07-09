"""Django 集成。

在 settings.py 中加入：

    MIDDLEWARE = [
        "apiwatch.integrations.django.ApiWatchDjangoMiddleware",
        ...
    ]
"""

from __future__ import annotations

from typing import Optional

from ..core.capture import build_event, start_capture
from ..core.client import ReportClient
from ..core.config import ApiWatchConfig


class ApiWatchDjangoMiddleware:
    """标准 Django middleware，采集请求级 API 调用事件。"""

    def __init__(self, get_response, config: Optional[ApiWatchConfig] = None) -> None:
        self.get_response = get_response
        self.config = self._build_config(config or ApiWatchConfig())
        self.client = ReportClient(self.config)

    def __call__(self, request):
        if not self.config.enabled:
            return self.get_response(request)

        request.apiwatch_capture = start_capture(self._inbound_traceparent(request))
        try:
            response = self.get_response(request)
        except Exception as exc:  # noqa: BLE001 - 采集后交还 Django 异常处理链
            self._emit(request, 500, type(exc).__name__, str(exc))
            raise

        self._emit(request, getattr(response, "status_code", 200))
        return response

    @staticmethod
    def _build_config(base: ApiWatchConfig) -> ApiWatchConfig:
        try:
            from django.conf import settings

            project = getattr(settings, "APIWATCH_PROJECT", None)
            collector_url = getattr(settings, "APIWATCH_COLLECTOR_URL", None)
            enabled = getattr(settings, "APIWATCH_ENABLED", None)
        except Exception:
            project = collector_url = enabled = None
        return base.with_overrides(
            project=project,
            collector_url=collector_url,
            enabled=enabled,
            framework="django",
        )

    @staticmethod
    def _inbound_traceparent(request) -> Optional[str]:
        try:
            headers = getattr(request, "headers", None)
            if headers is not None:
                value = headers.get("traceparent")
                if value:
                    return value
            return request.META.get("HTTP_TRACEPARENT")
        except Exception:
            return None

    @staticmethod
    def _extract_route(request) -> Optional[str]:
        try:
            match = getattr(request, "resolver_match", None)
            route = getattr(match, "route", None)
            if isinstance(route, str) and route:
                return route
            view_name = getattr(match, "view_name", None)
            if isinstance(view_name, str) and view_name:
                return view_name
        except Exception:
            return None
        return None

    def _emit(
        self,
        request,
        status_code: int,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        try:
            capture = getattr(request, "apiwatch_capture", None)
            if capture is None:
                return
            event = build_event(
                self.config,
                capture,
                method=request.method,
                path=request.path,
                status_code=status_code,
                route=self._extract_route(request),
                error_type=error_type,
                error_message=error_message,
            )
            self.client.report(event)
        except Exception:
            pass
