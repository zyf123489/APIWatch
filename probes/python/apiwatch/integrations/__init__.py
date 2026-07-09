"""APIWatch 框架集成层。"""

from .asgi import ApiWatchASGIMiddleware

__all__ = ["ApiWatchASGIMiddleware", "ApiWatchFlask", "ApiWatchDjangoMiddleware"]


def __getattr__(name):
    if name == "ApiWatchFlask":
        from .flask import ApiWatchFlask

        return ApiWatchFlask
    if name == "ApiWatchDjangoMiddleware":
        from .django import ApiWatchDjangoMiddleware

        return ApiWatchDjangoMiddleware
    raise AttributeError(name)
