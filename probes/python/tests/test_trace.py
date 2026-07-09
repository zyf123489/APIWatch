"""trace 标识生成与解析测试。"""

import re

from apiwatch.core.trace import (
    build_traceparent,
    generate_span_id,
    generate_trace_id,
    new_ids,
    parse_traceparent,
)

_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")


def test_generate_trace_id_is_32_hex():
    tid = generate_trace_id()
    assert _HEX32.match(tid)


def test_generate_span_id_is_16_hex():
    sid = generate_span_id()
    assert _HEX16.match(sid)


def test_generate_ids_are_random():
    assert generate_trace_id() != generate_trace_id()
    assert generate_span_id() != generate_span_id()


def test_build_traceparent_format():
    tid = "0123456789abcdef0123456789abcdef"
    sid = "0123456789abcdef"
    tp = build_traceparent(tid, sid)
    assert tp == f"00-{tid}-{sid}-01"


def test_build_traceparent_unsampled():
    tp = build_traceparent("a" * 32, "b" * 16, sampled=False)
    assert tp.endswith("-00")


def test_parse_traceparent_valid():
    tid = "0123456789abcdef0123456789abcdef"
    header = f"00-{tid}-0123456789abcdef-01"
    assert parse_traceparent(header) == tid


def test_parse_traceparent_uppercase_normalized():
    tid = "0123456789ABCDEF0123456789ABCDEF"
    header = f"00-{tid}-0123456789ABCDEF-01"
    assert parse_traceparent(header) == tid.lower()


def test_parse_traceparent_invalid_returns_none():
    assert parse_traceparent(None) is None
    assert parse_traceparent("") is None
    assert parse_traceparent("garbage") is None
    assert parse_traceparent("00-tooshort-0123456789abcdef-01") is None


def test_parse_traceparent_all_zero_trace_rejected():
    header = "00-" + "0" * 32 + "-0123456789abcdef-01"
    assert parse_traceparent(header) is None


def test_new_ids_without_inbound_creates_fresh():
    tid, sid = new_ids(None)
    assert _HEX32.match(tid)
    assert _HEX16.match(sid)


def test_new_ids_reuses_inbound_trace():
    tid = "0123456789abcdef0123456789abcdef"
    header = f"00-{tid}-0123456789abcdef-01"
    got_tid, got_sid = new_ids(header)
    assert got_tid == tid
    # span 始终新建，与入站 span 不同
    assert got_sid != "0123456789abcdef"
    assert _HEX16.match(got_sid)
