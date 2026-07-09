"""统一 API 调用事件模型。

对应 spec/event.schema.json（契约版本 1.0）。探针采集后统一产出该结构，
序列化为 JSON 上报到 collector 的 /events 接口。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Optional

# 与 spec/event.schema.json 的 schema_version 保持一致
SCHEMA_VERSION = "1.0"


@dataclass
class ApiEvent:
    """一次 API 请求对应的事件（请求级 / 粒度 1）。"""

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
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """转为契约字段字典（可直接 JSON 序列化）。"""
        return asdict(self)

    def to_json(self) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
