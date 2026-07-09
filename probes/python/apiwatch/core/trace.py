"""W3C Trace Context 标识生成与解析。

APIWatch 探针使用 W3C Trace Context 的 traceparent 格式，
天然支持跨语言、跨服务关联，并可与 OpenTelemetry 生态衔接。
详见 spec/SPEC.md 第 4 节。
"""

from __future__ import annotations

import re
import secrets

# traceparent: version-traceid-spanid-flags，如 00-<32hex>-<16hex>-01
_TRACEPARENT_RE = re.compile(
    r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$"
)

# W3C 规定的非法全零值
_INVALID_TRACE_ID = "0" * 32
_INVALID_SPAN_ID = "0" * 16


def generate_trace_id() -> str:
    """生成 32 位小写十六进制 trace-id（加密安全随机）。"""
    return secrets.token_hex(16)


def generate_span_id() -> str:
    """生成 16 位小写十六进制 span-id（加密安全随机）。"""
    return secrets.token_hex(8)


def build_traceparent(trace_id: str, span_id: str, sampled: bool = True) -> str:
    """按 W3C 格式拼装 traceparent：``00-{trace_id}-{span_id}-{flags}``。"""
    flags = "01" if sampled else "00"
    return f"00-{trace_id}-{span_id}-{flags}"


def parse_traceparent(header: str | None) -> str | None:
    """解析入站 traceparent，返回其中合法的 trace-id；非法或缺失返回 None。

    用于分布式串联：若上游已带 traceparent，则复用其 trace-id，
    使同一条链路在 collector 侧可被关联（为未来跨服务 tracing 铺路）。
    """
    if not header:
        return None
    match = _TRACEPARENT_RE.match(header.strip().lower())
    if not match:
        return None
    trace_id = match.group(2)
    if trace_id == _INVALID_TRACE_ID:
        return None
    return trace_id


def new_ids(inbound_traceparent: str | None = None) -> tuple[str, str]:
    """生成一对 (trace_id, span_id)。

    若入站 traceparent 合法，则复用其 trace-id；否则新建 trace-id。
    span-id 始终新建。
    """
    trace_id = parse_traceparent(inbound_traceparent) or generate_trace_id()
    span_id = generate_span_id()
    return trace_id, span_id
