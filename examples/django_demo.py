"""APIWatch Django 端到端验证示例。

运行前先启动 collector：

    apiwatch start

再启动本示例：

    python examples/django_demo.py
"""

from __future__ import annotations

import sys
import time

from django.conf import settings
from django.core.management import execute_from_command_line
from django.http import JsonResponse
from django.urls import path


def index(request):
    return JsonResponse(
        {
            "service": "apiwatch-django-demo",
            "try": ["/api/users/1/", "/api/slow/", "/api/boom/"],
        }
    )


def get_user(request, user_id: int):
    return JsonResponse({"id": user_id, "name": f"user-{user_id}"})


def slow(request):
    time.sleep(0.3)
    return JsonResponse({"ok": True, "note": "this endpoint is intentionally slow"})


def boom(request):
    raise ValueError("intentional demo error")


urlpatterns = [
    path("", index),
    path("api/users/<int:user_id>/", get_user),
    path("api/slow/", slow),
    path("api/boom/", boom),
]


def main() -> None:
    if not settings.configured:
        settings.configure(
            DEBUG=True,
            ROOT_URLCONF=__name__,
            SECRET_KEY="apiwatch-demo",
            ALLOWED_HOSTS=["127.0.0.1", "localhost"],
            MIDDLEWARE=["apiwatch.integrations.django.ApiWatchDjangoMiddleware"],
            APIWATCH_PROJECT="django-demo",
            DEFAULT_CHARSET="utf-8",
        )
    args = sys.argv
    if len(args) == 1:
        args = [args[0], "runserver", "127.0.0.1:8082"]
    execute_from_command_line(args)


if __name__ == "__main__":
    main()
