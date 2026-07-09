"""Collector 的请求 / 响应数据模型。

事件模型以 spec/event.schema.json（契约版本 1.0）为准。collector 只吃符合该契约的
JSON，因此这里的 EventIn 是契约在 Python 侧的映射，与探针的实现语言无关。
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


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
