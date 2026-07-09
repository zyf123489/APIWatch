"""Django 集成测试。"""

import pytest

django = pytest.importorskip("django")

from django.conf import settings
from django.http import JsonResponse
from django.test import Client, override_settings
from django.urls import path

from apiwatch.integrations.django import ApiWatchDjangoMiddleware


class _FakeClient:
    def __init__(self):
        self.events = []

    def report(self, event):
        self.events.append(event)


def user_view(request, user_id):
    return JsonResponse({"id": user_id})


def boom_view(request):
    raise ValueError("boom")


urlpatterns = [
    path("api/users/<int:user_id>/", user_view),
    path("api/boom/", boom_view),
]


if not settings.configured:
    settings.configure(
        DEBUG_PROPAGATE_EXCEPTIONS=True,
        ROOT_URLCONF=__name__,
        SECRET_KEY="apiwatch-tests",
        ALLOWED_HOSTS=["testserver"],
        MIDDLEWARE=["apiwatch.integrations.django.ApiWatchDjangoMiddleware"],
        APIWATCH_PROJECT="test",
        DEFAULT_CHARSET="utf-8",
    )
    django.setup()


def _patch_client(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(ApiWatchDjangoMiddleware, "client", fake, raising=False)
    original_init = ApiWatchDjangoMiddleware.__init__

    def patched_init(self, get_response, config=None):
        original_init(self, get_response, config)
        self.client = fake

    monkeypatch.setattr(ApiWatchDjangoMiddleware, "__init__", patched_init)
    return fake


@override_settings(APIWATCH_PROJECT="test", APIWATCH_ENABLED=True)
def test_django_normal_request_emits_event_and_route(monkeypatch):
    fake = _patch_client(monkeypatch)
    client = Client()

    response = client.get("/api/users/1/")

    assert response.status_code == 200
    assert len(fake.events) == 1
    event = fake.events[0]
    assert event.project == "test"
    assert event.framework == "django"
    assert event.method == "GET"
    assert event.path == "/api/users/1/"
    assert event.route == "api/users/<int:user_id>/"
    assert event.status_code == 200
    assert event.error_type is None


@override_settings(APIWATCH_PROJECT="test", APIWATCH_ENABLED=True)
def test_django_exception_records_500_and_reraises(monkeypatch):
    fake = _patch_client(monkeypatch)
    client = Client(raise_request_exception=True)

    with pytest.raises(ValueError):
        client.get("/api/boom/")

    assert len(fake.events) == 1
    event = fake.events[0]
    assert event.status_code == 500
    assert event.error_type == "ValueError"
    assert event.error_message == "boom"


@override_settings(APIWATCH_PROJECT="test", APIWATCH_ENABLED=True)
def test_django_inbound_traceparent_reused(monkeypatch):
    fake = _patch_client(monkeypatch)
    client = Client()
    tid = "0123456789abcdef0123456789abcdef"
    traceparent = f"00-{tid}-0123456789abcdef-01"

    client.get("/api/users/1/", HTTP_TRACEPARENT=traceparent)

    assert fake.events[0].trace_id == tid


@override_settings(APIWATCH_PROJECT="test", APIWATCH_ENABLED=False)
def test_django_enabled_false_suppresses_events(monkeypatch):
    fake = _patch_client(monkeypatch)
    client = Client()

    response = client.get("/api/users/1/")

    assert response.status_code == 200
    assert fake.events == []
