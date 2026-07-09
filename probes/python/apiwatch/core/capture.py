"""共享请求采集工具。

各框架集成负责从自身请求对象里取 method/path/status/route/error，
本模块负责统一生成 trace 标识、时间戳与 ApiEvent。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .config import ApiWatchConfig
from .event import ApiEvent
from .trace import build_traceparent, new_ids


@dataclass
class RequestCapture:
    """一次请求的采集上下文。"""

    start: float
    timestamp: str
    trace_id: str
    span_id: str


def start_capture(inbound_traceparent: str | None = None) -> RequestCapture:
    """开始一次请求采集，并生成/复用 trace 标识。"""
    trace_id, span_id = new_ids(inbound_traceparent)
    return RequestCapture(
        start=time.perf_counter(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        trace_id=trace_id,
        span_id=span_id,
    )


def build_event(
    config: ApiWatchConfig,
    capture: RequestCapture,
    method: str,
    path: str,
    status_code: int,
    route: Optional[str] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
) -> ApiEvent:
    """按统一契约组装请求事件。"""
    duration_ms = (time.perf_counter() - capture.start) * 1000.0
    return ApiEvent(
        project=config.project,
        framework=config.framework,
        method=method,
        path=path,
        route=route,
        status_code=status_code,
        duration_ms=round(duration_ms, 3),
        trace_id=capture.trace_id,
        span_id=capture.span_id,
        traceparent=build_traceparent(capture.trace_id, capture.span_id),
        timestamp=capture.timestamp,
        error_type=error_type,
        error_message=error_message,
    )
