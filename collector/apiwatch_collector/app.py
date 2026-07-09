"""Collector 的 FastAPI 应用。

职责：接收探针上报的事件、写入 SQLite、提供聚合查询与看板。
与探针的实现语言无关——只吃符合 spec/event.schema.json 的 JSON。

环境变量：
- ``APIWATCH_DB``  SQLite 文件路径，默认 apiwatch.db（当前工作目录）
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional, Union

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .aggregate import build_apis, build_summary
from .models import ApisOut, EventIn, RequestsOut, SummaryOut
from .storage import Storage

DB_PATH = os.environ.get("APIWATCH_DB", "apiwatch.db")
_DASHBOARD_FILE = Path(__file__).parent / "dashboard" / "index.html"

storage = Storage(DB_PATH)

app = FastAPI(title="APIWatch Collector", version="0.2.0")

# 本地开发工具：允许跨端口访问（B 模式看板挂在业务应用端口时需要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _dump(model: Any) -> dict:
    """兼容 pydantic v1/v2 的序列化。"""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


@app.post("/events", status_code=202)
def ingest_events(payload: Union[List[EventIn], EventIn]) -> dict:
    """接收探针上报的事件，支持单条对象或数组批量。"""
    events = payload if isinstance(payload, list) else [payload]
    written = storage.insert_events([_dump(e) for e in events])
    return {"accepted": written}


@app.get("/summary", response_model=SummaryOut)
def get_summary(project: Optional[str] = None, framework: Optional[str] = None) -> dict:
    return build_summary(storage.fetch_agg_rows(project, framework))


@app.get("/apis", response_model=ApisOut)
def get_apis(project: Optional[str] = None, framework: Optional[str] = None) -> dict:
    return build_apis(storage.fetch_agg_rows(project, framework))


@app.get("/requests", response_model=RequestsOut)
def get_requests(
    limit: int = 50,
    offset: int = 0,
    project: Optional[str] = None,
    framework: Optional[str] = None,
) -> dict:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    return {
        "total": storage.total_count(project, framework),
        "limit": limit,
        "offset": offset,
        "requests": storage.recent(limit, offset, project, framework),
    }


@app.get("/requests/{trace_id}")
def get_request_detail(trace_id: str) -> dict:
    return {"trace_id": trace_id, "spans": storage.by_trace(trace_id)}


@app.get("/filters")
def get_filters() -> dict:
    return {
        "projects": storage.distinct_values("project"),
        "frameworks": storage.distinct_values("framework"),
    }


@app.delete("/events")
def clear_events(project: Optional[str] = None) -> dict:
    return {"deleted": storage.clear_events(project), "project": project}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> Response:
    if _DASHBOARD_FILE.exists():
        return FileResponse(_DASHBOARD_FILE, media_type="text/html")
    return HTMLResponse(
        "<h1>APIWatch</h1><p>dashboard/index.html 未找到。</p>", status_code=200
    )


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")
