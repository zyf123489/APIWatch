"""Flask 集成测试。"""

import pytest

flask = pytest.importorskip("flask")

from apiwatch.integrations.flask import ApiWatchFlask


class _FakeClient:
    def __init__(self):
        self.events = []

    def report(self, event):
        self.events.append(event)


def _make_app():
    app = flask.Flask(__name__)
    app.testing = True
    ApiWatchFlask(app, project="test")
    fake = _FakeClient()
    app.extensions["apiwatch"]["client"] = fake

    @app.get("/api/users/<int:user_id>")
    def user(user_id):
        return {"id": user_id}

    @app.get("/api/boom")
    def boom():
        raise ValueError("boom")

    return app, fake


def test_flask_normal_request_emits_event_and_route():
    app, fake = _make_app()
    client = app.test_client()

    response = client.get("/api/users/1")

    assert response.status_code == 200
    assert len(fake.events) == 1
    event = fake.events[0]
    assert event.project == "test"
    assert event.framework == "flask"
    assert event.method == "GET"
    assert event.path == "/api/users/1"
    assert event.route == "/api/users/<int:user_id>"
    assert event.status_code == 200
    assert event.error_type is None


def test_flask_404_uses_path_fallback():
    app, fake = _make_app()
    client = app.test_client()

    response = client.get("/missing")

    assert response.status_code == 404
    assert len(fake.events) == 1
    assert fake.events[0].path == "/missing"
    assert fake.events[0].route is None
    assert fake.events[0].status_code == 404


def test_flask_exception_records_500_and_reraises():
    app, fake = _make_app()
    client = app.test_client()

    with pytest.raises(ValueError):
        client.get("/api/boom")

    assert len(fake.events) == 1
    event = fake.events[0]
    assert event.status_code == 500
    assert event.error_type == "ValueError"
    assert event.error_message == "boom"


def test_flask_handled_exception_records_error_type():
    app, fake = _make_app()
    app.testing = False
    client = app.test_client()

    response = client.get("/api/boom")

    assert response.status_code == 500
    assert len(fake.events) == 1
    event = fake.events[0]
    assert event.status_code == 500
    assert event.error_type == "ValueError"
    assert event.error_message == "boom"


def test_flask_inbound_traceparent_reused():
    app, fake = _make_app()
    client = app.test_client()
    tid = "0123456789abcdef0123456789abcdef"
    traceparent = f"00-{tid}-0123456789abcdef-01"

    client.get("/api/users/1", headers={"traceparent": traceparent})

    assert fake.events[0].trace_id == tid
