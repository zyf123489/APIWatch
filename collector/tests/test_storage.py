"""SQLite 存储层测试。"""

from apiwatch_collector.storage import Storage


def _event(**overrides):
    ev = {
        "schema_version": "1.0",
        "project": "test",
        "framework": "fastapi",
        "method": "GET",
        "path": "/api/users/1",
        "route": "/api/users/{id}",
        "status_code": 200,
        "duration_ms": 12.5,
        "trace_id": "0123456789abcdef0123456789abcdef",
        "span_id": "0123456789abcdef",
        "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        "timestamp": "2026-07-08T12:00:00+08:00",
        "error_type": None,
        "error_message": None,
    }
    ev.update(overrides)
    return ev


def test_insert_and_count(tmp_path):
    st = Storage(str(tmp_path / "t.db"))
    assert st.total_count() == 0
    n = st.insert_events([_event(), _event(path="/api/x")])
    assert n == 2
    assert st.total_count() == 2
    st.close()


def test_insert_empty_returns_zero(tmp_path):
    st = Storage(str(tmp_path / "t.db"))
    assert st.insert_events([]) == 0
    st.close()


def test_recent_is_desc(tmp_path):
    st = Storage(str(tmp_path / "t.db"))
    st.insert_events([_event(path="/a"), _event(path="/b"), _event(path="/c")])
    rows = st.recent(limit=10)
    # 最近插入的在最前（id 倒序）
    assert rows[0]["path"] == "/c"
    assert rows[-1]["path"] == "/a"
    st.close()


def test_recent_limit_offset(tmp_path):
    st = Storage(str(tmp_path / "t.db"))
    st.insert_events([_event(path=f"/p{i}") for i in range(5)])
    page = st.recent(limit=2, offset=0)
    assert len(page) == 2
    assert page[0]["path"] == "/p4"
    st.close()


def test_fetch_agg_rows_columns(tmp_path):
    st = Storage(str(tmp_path / "t.db"))
    st.insert_events([_event()])
    rows = st.fetch_agg_rows()
    assert len(rows) == 1
    assert set(rows[0].keys()) == {"route", "path", "duration_ms", "status_code", "error_type"}
    st.close()


def test_by_trace(tmp_path):
    st = Storage(str(tmp_path / "t.db"))
    st.insert_events([
        _event(trace_id="a" * 32),
        _event(trace_id="b" * 32),
    ])
    rows = st.by_trace("a" * 32)
    assert len(rows) == 1
    assert rows[0]["trace_id"] == "a" * 32
    st.close()


def test_missing_optional_field_defaults_none(tmp_path):
    st = Storage(str(tmp_path / "t.db"))
    ev = _event()
    del ev["route"]  # 缺失可选字段
    st.insert_events([ev])
    rows = st.fetch_agg_rows()
    assert rows[0]["route"] is None
    st.close()


def test_filters_by_project_and_framework(tmp_path):
    st = Storage(str(tmp_path / "t.db"))
    st.insert_events([
        _event(project="a", framework="fastapi", path="/a"),
        _event(project="b", framework="flask", path="/b"),
        _event(project="a", framework="django", path="/c"),
    ])
    assert st.total_count(project="a") == 2
    assert st.total_count(framework="flask") == 1
    assert st.recent(project="b")[0]["path"] == "/b"
    assert len(st.fetch_agg_rows(project="a", framework="django")) == 1
    assert st.distinct_values("project") == ["a", "b"]
    st.close()


def test_clear_events_all_and_by_project(tmp_path):
    st = Storage(str(tmp_path / "t.db"))
    st.insert_events([
        _event(project="keep", path="/a"),
        _event(project="drop", path="/b"),
        _event(project="drop", path="/c"),
    ])
    assert st.clear_events(project="drop") == 2
    assert st.total_count() == 1
    assert st.recent()[0]["project"] == "keep"
    assert st.clear_events() == 1
    assert st.total_count() == 0
    st.close()
