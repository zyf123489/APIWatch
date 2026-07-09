"""Collector API 端点测试（FastAPI TestClient）。

在导入 app 之前将 APIWATCH_DB 指向临时库，避免污染工作目录的 apiwatch.db。
运行测试需额外安装：pytest、httpx（TestClient 依赖）。
"""

import os
import tempfile

# 必须在 import app 之前设置，模块级 storage 才会指向临时库
_TMPDIR = tempfile.mkdtemp()
os.environ["APIWATCH_DB"] = os.path.join(_TMPDIR, "test_api.db")

from fastapi.testclient import TestClient  # noqa: E402

from apiwatch_collector.app import app  # noqa: E402

client = TestClient(app)


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


def test_post_single_event():
    r = client.post("/events", json=_event())
    assert r.status_code == 202
    assert r.json()["accepted"] == 1


def test_post_batch_events():
    r = client.post("/events", json=[_event(path="/a"), _event(path="/b")])
    assert r.status_code == 202
    assert r.json()["accepted"] == 2


def test_summary_shape():
    client.post("/events", json=_event(duration_ms=50.0))
    r = client.get("/summary")
    assert r.status_code == 200
    body = r.json()
    for key in ("total_requests", "avg_duration_ms", "p95_duration_ms", "error_rate", "error_count"):
        assert key in body
    assert body["total_requests"] >= 1


def test_apis_shape():
    client.post("/events", json=_event(route="/api/z", path="/api/z"))
    r = client.get("/apis")
    assert r.status_code == 200
    assert "apis" in r.json()
    assert isinstance(r.json()["apis"], list)


def test_requests_pagination_shape():
    client.post("/events", json=_event())
    r = client.get("/requests?limit=5&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 5
    assert body["offset"] == 0
    assert "requests" in body
    assert "total" in body


def test_request_detail_by_trace():
    tid = "f" * 32
    client.post("/events", json=_event(trace_id=tid))
    r = client.get(f"/requests/{tid}")
    assert r.status_code == 200
    body = r.json()
    assert body["trace_id"] == tid
    assert isinstance(body["spans"], list)
    assert len(body["spans"]) >= 1


def test_error_event_counted():
    client.post("/events", json=_event(status_code=500, error_type="ValueError", error_message="boom"))
    r = client.get("/summary")
    assert r.json()["error_count"] >= 1


def test_filters_endpoint_and_query_filters():
    client.delete("/events")
    client.post("/events", json=[
        _event(project="api-a", framework="fastapi", path="/a", route="/a"),
        _event(project="api-b", framework="flask", path="/b", route="/b"),
    ])

    filters = client.get("/filters").json()
    assert "api-a" in filters["projects"]
    assert "flask" in filters["frameworks"]

    summary = client.get("/summary?project=api-a").json()
    assert summary["total_requests"] == 1
    apis = client.get("/apis?framework=flask").json()["apis"]
    assert len(apis) == 1
    assert apis[0]["path"] == "/b"
    requests = client.get("/requests?project=api-b").json()
    assert requests["total"] == 1
    assert requests["requests"][0]["project"] == "api-b"


def test_delete_events_clears_all_and_project():
    client.delete("/events")
    client.post("/events", json=[
        _event(project="keep", path="/keep"),
        _event(project="drop", path="/drop1"),
        _event(project="drop", path="/drop2"),
    ])

    r = client.delete("/events?project=drop")
    assert r.status_code == 200
    assert r.json()["deleted"] == 2
    assert client.get("/summary").json()["total_requests"] == 1

    r = client.delete("/events")
    assert r.status_code == 200
    assert r.json()["deleted"] == 1
    assert client.get("/summary").json()["total_requests"] == 0


def test_dashboard_contains_stability_controls():
    r = client.get("/dashboard")
    assert r.status_code == 200
    html = r.text
    assert 'id="project-filter"' in html
    assert 'id="framework-filter"' in html
    assert 'id="clear-btn"' in html
    assert "/filters" in html
    assert 'sendJSON(path, "DELETE")' in html or 'sendJSON(path, "DELETE");' in html
