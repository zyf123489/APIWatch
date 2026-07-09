"""探针配置。

支持代码传参与环境变量两种方式，环境变量优先级低于显式传参、高于默认值：

- ``APIWATCH_COLLECTOR_URL``  collector 基地址，默认 http://127.0.0.1:8765
- ``APIWATCH_PROJECT``        项目名，默认 "default"
- ``APIWATCH_ENABLED``        是否启用采集，默认 true（"0"/"false"/"no" 视为关闭）
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

_DEFAULT_COLLECTOR_URL = "http://127.0.0.1:8765"
_DEFAULT_PROJECT = "default"
_FALSY = {"0", "false", "no", "off", ""}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSY


@dataclass
class ApiWatchConfig:
    """探针运行配置。"""

    collector_url: str = field(
        default_factory=lambda: os.environ.get(
            "APIWATCH_COLLECTOR_URL", _DEFAULT_COLLECTOR_URL
        ).rstrip("/")
    )
    project: str = field(
        default_factory=lambda: os.environ.get("APIWATCH_PROJECT", _DEFAULT_PROJECT)
    )
    enabled: bool = field(default_factory=lambda: _env_bool("APIWATCH_ENABLED", True))
    framework: str = "asgi"
    # 上报队列上限，满则丢弃最旧事件，防止内存膨胀
    queue_maxsize: int = 1000
    # 单次上报的网络超时（秒）
    timeout: float = 1.0

    @property
    def events_url(self) -> str:
        """事件上报接口完整地址。"""
        return f"{self.collector_url}/events"

    def with_overrides(self, **kwargs) -> "ApiWatchConfig":
        """基于当前配置生成一个覆盖了部分字段的新配置。"""
        data = self.__dict__.copy()
        data.update({k: v for k, v in kwargs.items() if v is not None})
        return ApiWatchConfig(**data)
