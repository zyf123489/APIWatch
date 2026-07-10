"""Collector 的 FastAPI 应用。

默认仅面向本机开发。绑定到非回环地址时，CLI 必须配置访问 Token；探针使用
Bearer Header，上报看板通过一次性 token query 建立 HttpOnly session Cookie。
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Optional, Union

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from .aggregate import build_apis, build_summary
from .models import ApisOut, EventIn, RequestsOut, SummaryOut
from .storage import Storage

_DASHBOARD_FILE = Path(__file__).parent / "dashboard" / "index.html"
_MAX_EVENT_BATCH = 1000
_MAX_BODY_BYTES = 1024 * 1024


@dataclass(frozen=True)
class CollectorSettings:
    """运行时配置。Token 存在时所有数据接口都需要认证。"""

    db_path: str = "apiwatch.db"
    token: Optional[str] = None
    max_body_bytes: int = _MAX_BODY_BYTES

    def __post_init__(self) -> None:
        if self.max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be positive")
        if self.token is not None:
            token = self.token.strip()
            if len(token) < 32:
                raise ValueError("APIWATCH_TOKEN must contain at least 32 characters")
            object.__setattr__(self, "token", token)

    @classmethod
    def from_env(cls) -> "CollectorSettings":
        raw_limit = os.environ.get("APIWATCH_MAX_BODY_BYTES", str(_MAX_BODY_BYTES))
        try:
            max_body_bytes = int(raw_limit)
        except ValueError as exc:
            raise ValueError("APIWATCH_MAX_BODY_BYTES must be an integer") from exc
        return cls(
            db_path=os.environ.get("APIWATCH_DB", "apiwatch.db"),
            token=os.environ.get("APIWATCH_TOKEN") or None,
            max_body_bytes=max_body_bytes,
        )


class RequestBodyLimitMiddleware:
    """Buffer at most the configured body limit before FastAPI parses JSON."""

    def __init__(self, app, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    if int(value) > self.max_body_bytes:
                        await self._send_too_large(send)
                        return
                except ValueError:
                    pass

        messages = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message.get("type") != "http.request":
                break
            total += len(message.get("body", b""))
            if total > self.max_body_bytes:
                await self._send_too_large(send)
                return
            if not message.get("more_body", False):
                break

        async def replay_receive():
            if messages:
                return messages.pop(0)
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _send_too_large(send) -> None:
        body = b'{"detail":"request body exceeds the APIWatch limit"}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _request_token(request: Request) -> Optional[str]:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:]
    return request.cookies.get("apiwatch_session")


def _authorized(request: Request, settings: CollectorSettings) -> bool:
    if not settings.token:
        return True
    candidate = _request_token(request)
    return candidate is not None and secrets.compare_digest(candidate, settings.token)


def _dump(model: Any) -> dict:
    """兼容 pydantic v1/v2 的序列化。"""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def create_app(
    settings: Optional[CollectorSettings] = None,
    storage_instance: Optional[Storage] = None,
) -> FastAPI:
    """构造可独立测试的 Collector 应用，同时保留模块级 ``app`` 入口。"""
    active_settings = settings or CollectorSettings.from_env()
    active_storage = storage_instance or Storage(active_settings.db_path)

    app = FastAPI(title="APIWatch Collector", version="0.3.1")
    app.state.settings = active_settings
    app.state.storage = active_storage
    app.add_middleware(
        RequestBodyLimitMiddleware, max_body_bytes=active_settings.max_body_bytes
    )

    def require_auth(request: Request) -> None:
        if not _authorized(request, active_settings):
            raise HTTPException(status_code=401, detail="APIWatch authentication required")

    @app.get("/health")
    def health() -> dict:
        return {"service": "apiwatch-collector", "version": "0.3.1"}

    @app.post("/events", status_code=202)
    def ingest_events(
        payload: Union[List[EventIn], EventIn],
        _: None = Depends(require_auth),
    ) -> dict:
        """接收严格 1.0 事件，支持单条对象或有限大小的数组。"""
        events = payload if isinstance(payload, list) else [payload]
        if len(events) > _MAX_EVENT_BATCH:
            raise HTTPException(
                status_code=422,
                detail=f"event batch exceeds the {_MAX_EVENT_BATCH} event limit",
            )
        written = active_storage.insert_events([_dump(event) for event in events])
        return {"accepted": written}

    @app.get("/summary", response_model=SummaryOut)
    def get_summary(
        project: Optional[str] = None,
        framework: Optional[str] = None,
        _: None = Depends(require_auth),
    ) -> dict:
        return build_summary(active_storage.fetch_agg_rows(project, framework))

    @app.get("/apis", response_model=ApisOut)
    def get_apis(
        project: Optional[str] = None,
        framework: Optional[str] = None,
        _: None = Depends(require_auth),
    ) -> dict:
        return build_apis(active_storage.fetch_agg_rows(project, framework))

    @app.get("/requests", response_model=RequestsOut)
    def get_requests(
        limit: int = 50,
        offset: int = 0,
        project: Optional[str] = None,
        framework: Optional[str] = None,
        _: None = Depends(require_auth),
    ) -> dict:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        return {
            "total": active_storage.total_count(project, framework),
            "limit": limit,
            "offset": offset,
            "requests": active_storage.recent(limit, offset, project, framework),
        }

    @app.get("/requests/{trace_id}")
    def get_request_detail(trace_id: str, _: None = Depends(require_auth)) -> dict:
        return {"trace_id": trace_id, "spans": active_storage.by_trace(trace_id)}

    @app.get("/filters")
    def get_filters(_: None = Depends(require_auth)) -> dict:
        return {
            "projects": active_storage.distinct_values("project"),
            "frameworks": active_storage.distinct_values("framework"),
        }

    @app.delete("/events")
    def clear_events(
        project: Optional[str] = None, _: None = Depends(require_auth)
    ) -> dict:
        return {"deleted": active_storage.clear_events(project), "project": project}

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request, token: Optional[str] = None) -> Response:
        if active_settings.token:
            if token is not None:
                if not secrets.compare_digest(token, active_settings.token):
                    raise HTTPException(status_code=401, detail="invalid APIWatch token")
                response = RedirectResponse(url="/dashboard", status_code=303)
                response.set_cookie(
                    "apiwatch_session",
                    active_settings.token,
                    httponly=True,
                    samesite="strict",
                    path="/",
                )
                response.headers["Cache-Control"] = "no-store"
                response.headers["Referrer-Policy"] = "no-referrer"
                return response
            require_auth(request)
        if _DASHBOARD_FILE.exists():
            return FileResponse(_DASHBOARD_FILE, media_type="text/html")
        return HTMLResponse(
            "<h1>APIWatch</h1><p>dashboard/index.html 未找到。</p>", status_code=200
        )

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse(url="/dashboard")

    return app


app = create_app()
storage = app.state.storage

