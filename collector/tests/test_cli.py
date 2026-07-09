"""Collector CLI 测试。"""

import io
from contextlib import redirect_stdout

from apiwatch_collector import cli


def _run(argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(argv)
    return code, out.getvalue()


def test_doctor_success(monkeypatch):
    def fake_request(url, method="GET"):
        assert url == "http://127.0.0.1:8765/summary"
        assert method == "GET"
        return 200, {"total_requests": 3}, None

    monkeypatch.setattr(cli, "_request_json", fake_request)
    code, out = _run(["doctor"])
    assert code == 0
    assert "collector: OK" in out
    assert "requests: 3" in out


def test_doctor_unavailable(monkeypatch):
    monkeypatch.setattr(
        cli, "_request_json", lambda url, method="GET": (0, None, "refused")
    )
    code, out = _run(["doctor"])
    assert code == 1
    assert "collector: unavailable" in out


def test_clear_success_with_project(monkeypatch):
    seen = {}

    def fake_request(url, method="GET"):
        seen["url"] = url
        seen["method"] = method
        return 200, {"deleted": 2, "project": "demo"}, None

    monkeypatch.setattr(cli, "_request_json", fake_request)
    code, out = _run(["clear", "--project", "demo"])
    assert code == 0
    assert seen == {
        "url": "http://127.0.0.1:8765/events?project=demo",
        "method": "DELETE",
    }
    assert "cleared: 2 events" in out


def test_clear_failure(monkeypatch):
    monkeypatch.setattr(
        cli, "_request_json", lambda url, method="GET": (0, None, "refused")
    )
    code, out = _run(["clear"])
    assert code == 1
    assert "clear failed" in out
