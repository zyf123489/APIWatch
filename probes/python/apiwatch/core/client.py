"""fire-and-forget 上报客户端。

设计底线（对应 spec/SPEC.md 与 idea 笔记难点 3）：
- 上报绝不阻塞、绝不影响业务请求。
- collector 不可用 / 超时 / 报错时静默丢弃。
- 后台单线程消费队列；队列满则丢弃最旧事件，防止内存膨胀。
"""

from __future__ import annotations

import json
import queue
import threading
import urllib.error
import urllib.request
from typing import Optional

from .config import ApiWatchConfig
from .event import ApiEvent


class ReportClient:
    """异步事件上报客户端（fire-and-forget）。"""

    def __init__(self, config: ApiWatchConfig) -> None:
        self._config = config
        self._queue: "queue.Queue[ApiEvent]" = queue.Queue(
            maxsize=config.queue_maxsize
        )
        self._worker: Optional[threading.Thread] = None
        self._started = False
        self._lock = threading.Lock()

    def _ensure_worker(self) -> None:
        """延迟启动后台消费线程（首次上报时）。"""
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            self._worker = threading.Thread(
                target=self._run,
                name="apiwatch-report",
                daemon=True,
            )
            self._worker.start()
            self._started = True

    def report(self, event: ApiEvent) -> None:
        """将事件放入上报队列（非阻塞）。队列满则丢弃最旧事件。"""
        if not self._config.enabled:
            return
        self._ensure_worker()
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            # 丢弃最旧，腾位给最新；任何异常都不得冒泡到业务
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(event)
            except Exception:
                pass

    def _run(self) -> None:
        while True:
            event = self._queue.get()
            try:
                self._send(event)
            except Exception:
                # 上报失败静默丢弃，绝不影响业务
                pass
            finally:
                self._queue.task_done()

    def _send(self, event: ApiEvent) -> None:
        data = json.dumps(event.to_dict(), ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self._config.events_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._config.timeout):
                pass
        except (urllib.error.URLError, OSError):
            # collector 不可用：静默丢弃
            pass
