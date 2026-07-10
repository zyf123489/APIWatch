"""Collector 的请求 / 响应数据模型。

事件模型以 spec/event.schema.json（契约版本 1.0）为准。collector 只吃符合该契约的
JSON，因此这里的 EventIn 是契约在 Python 侧的映射，与探针的实现语言无关。
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, root_validator, validator


_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_TRACEPARENT_RE = re.compile(
    r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$"
)
_HTTP_TOKEN_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")

_ZERO_TRACE_ID = "0" * 32
_ZERO_SPAN_ID = "0" * 16


def _parse_timestamp(value: str) -> None:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("timestamp must be an ISO 8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")


class EventIn(BaseModel):
    """探针上报的单个 API 调用事件（对应 spec/event.schema.json）。"""

    schema_version: str
    project: str
    framework: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    trace_id: str
    span_id: str
    traceparent: str
    timestamp: str
    route: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        extra = "forbid"

    @validator("schema_version")
    def validate_schema_version(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError("unsupported schema_version")
        return value

    @validator("project")
    def validate_project(cls, value: str) -> str:
        if not value.strip() or len(value) > 128:
            raise ValueError("project must be 1..128 non-whitespace characters")
        return value

    @validator("framework")
    def validate_framework(cls, value: str) -> str:
        if not value.strip() or len(value) > 64:
            raise ValueError("framework must be 1..64 non-whitespace characters")
        return value

    @validator("method")
    def validate_method(cls, value: str) -> str:
        if len(value) > 32 or not _HTTP_TOKEN_RE.fullmatch(value):
            raise ValueError("method must be a valid HTTP token up to 32 characters")
        return value

    @validator("path")
    def validate_path(cls, value: str) -> str:
        if not value or len(value) > 2048:
            raise ValueError("path must be 1..2048 characters")
        return value

    @validator("route")
    def validate_route(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and len(value) > 2048:
            raise ValueError("route must be at most 2048 characters")
        return value

    @validator("status_code", pre=True)
    def validate_status_type(cls, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("status_code must be an integer")
        return value

    @validator("status_code")
    def validate_status_code(cls, value: int) -> int:
        if value < 100 or value > 599:
            raise ValueError("status_code must be between 100 and 599")
        return value

    @validator("duration_ms", pre=True)
    def validate_duration_type(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("duration_ms must be a number")
        return value

    @validator("duration_ms")
    def validate_duration(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("duration_ms must be finite and non-negative")
        return value

    @validator("trace_id")
    def validate_trace_id(cls, value: str) -> str:
        if value == _ZERO_TRACE_ID or not _TRACE_ID_RE.fullmatch(value):
            raise ValueError("trace_id must be a non-zero 32-character lowercase hex value")
        return value

    @validator("span_id")
    def validate_span_id(cls, value: str) -> str:
        if value == _ZERO_SPAN_ID or not _SPAN_ID_RE.fullmatch(value):
            raise ValueError("span_id must be a non-zero 16-character lowercase hex value")
        return value

    @validator("traceparent")
    def validate_traceparent(cls, value: str) -> str:
        match = _TRACEPARENT_RE.fullmatch(value)
        if not match or match.group(1) == _ZERO_TRACE_ID or match.group(2) == _ZERO_SPAN_ID:
            raise ValueError("traceparent must contain non-zero W3C version 00 identifiers")
        return value

    @validator("timestamp")
    def validate_timestamp(cls, value: str) -> str:
        if len(value) > 64:
            raise ValueError("timestamp must be at most 64 characters")
        _parse_timestamp(value)
        return value

    @validator("error_type")
    def validate_error_type(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and len(value) > 256:
            raise ValueError("error_type must be at most 256 characters")
        return value

    @validator("error_message")
    def validate_error_message(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and len(value) > 4096:
            raise ValueError("error_message must be at most 4096 characters")
        return value

    @root_validator(skip_on_failure=True)
    def validate_trace_consistency(cls, values):
        match = _TRACEPARENT_RE.fullmatch(values["traceparent"])
        if match.group(1) != values["trace_id"] or match.group(2) != values["span_id"]:
            raise ValueError("traceparent identifiers must match trace_id and span_id")
        return values


class ApiStat(BaseModel):
    """单个接口（按 route 兜底 path 聚合）的统计。"""

    route: Optional[str] = None
    path: str
    count: int
    avg_ms: float
    p95_ms: float
    max_ms: float
    error_count: int
    error_rate: float


class SummaryOut(BaseModel):
    """全局汇总指标。"""

    total_requests: int
    avg_duration_ms: float
    p95_duration_ms: float
    error_rate: float
    error_count: int


class ApisOut(BaseModel):
    """接口聚合列表。"""

    apis: List[ApiStat]


class RequestRow(BaseModel):
    """最近请求列表中的一行 / 单请求详情。"""

    id: int
    project: str
    framework: str
    method: str
    path: str
    route: Optional[str] = None
    status_code: int
    duration_ms: float
    trace_id: str
    span_id: str
    traceparent: str
    timestamp: str
    error_type: Optional[str] = None
    error_message: Optional[str] = None


class RequestsOut(BaseModel):
    """最近请求分页结果。"""

    total: int
    limit: int
    offset: int
    requests: List[RequestRow]
