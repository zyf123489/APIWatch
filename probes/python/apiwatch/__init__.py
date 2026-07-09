"""APIWatch · Python 探针。

面向本地开发态的多框架 API 调用观测探针。接入一行 middleware，即可采集请求级
API 调用事件并上报到本地 collector，在看板上查看耗时、次数、错误率与 trace 信息。

    from fastapi import FastAPI
    from apiwatch.integrations.asgi import ApiWatchASGIMiddleware

    app = FastAPI()
    app.add_middleware(ApiWatchASGIMiddleware)
"""

from __future__ import annotations

from .core.config import ApiWatchConfig
from .core.event import SCHEMA_VERSION, ApiEvent
from .integrations.asgi import ApiWatchASGIMiddleware

__version__ = "0.2.0"

__all__ = [
    "ApiWatchASGIMiddleware",
    "ApiWatchConfig",
    "ApiEvent",
    "SCHEMA_VERSION",
    "__version__",
]
