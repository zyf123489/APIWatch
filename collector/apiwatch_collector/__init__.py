"""APIWatch Collector · 本地采集与可视化服务。

语言无关：只接收符合 spec/event.schema.json 的 JSON 事件，存入 SQLite，
提供聚合查询与本地看板。未来任何语言的探针都可复用同一个 collector。
"""

from __future__ import annotations

__version__ = "0.2.0"

__all__ = ["__version__"]
