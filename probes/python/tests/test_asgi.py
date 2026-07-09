"""ASGI 中间件测试：事件组装、状态捕获、异常路径、route 兜底、trace 复用。

不引入 pytest-asyncio：用 asyncio.run 在同步测试函数里驱动 middleware。
用 FakeClient 替换探针的上报客户端，捕获事件而不走网络。
"""

import asyncio

import pytest

from apiwatch.integrations.asgi import ApiWatchASGIMiddleware


class _FakeClient:
    def __init__(self):
        self.events = []

    def report(self, event):
        self.events.append(event)


class _FakeRoute:
    """模拟 Starlette/FastAPI 路由匹配后写入 scope 的 route 对象。"""

    def __init__(self, path_format):
        self.path_format = path_format


def _run(method="GET", path="/x", headers=None, app_status=200,
         raise_exc=None, route=None):
    """驱动一次 http 请求，返回 (captured_events, sent_messages, raised)。"""
    fake = _FakeClient()

    async def downstream(scope, receive, send):
        if route is not None:
            scope["route"] = _FakeRoute(route)  # 模拟路由匹配写入 scope
        if raise_exc is not None:
            raise raise_exc
        await send({"type": "http.response.start", "status": app_status, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = ApiWatchASGIMiddleware(downstream, project="test", framework="fastapi")
    mw._client = fake  # 替换上报客户端，捕获事件

    scope = {"type": "http", "method": method, "path": path, "headers": headers or []}
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    raised = None

    async def go():
        await mw(scope, receive, send)

    try:
        asyncio.run(go())
    except Exception as exc:  # noqa: BLE001
        raised = exc

    return fake.events, sent, raised


def test_normal_request_emits_event():
    events, sent, raised = _run(method="GET", path="/api/ping", app_status=200)
    assert raised is None
    assert len(events) == 1
    ev = events[0]
    assert ev.method == "GET"
    assert ev.path == "/api/ping"
    assert ev.status_code == 200
    assert ev.error_type is None
    assert ev.error_message is None
    assert ev.project == "test"
    assert ev.framework == "fastapi"
    assert ev.duration_ms >= 0


def test_status_code_captured_from_response():
    events, _, _ = _run(app_status=404)
    assert events[0].status_code == 404


def test_exception_path_reraises_and_records_500():
    events, _, raised = _run(path="/boom", raise_exc=ValueError("boom"))
    # 异常必须原样抛出，不被吞掉
    assert isinstance(raised, ValueError)
    assert len(events) == 1
    ev = events[0]
    assert ev.status_code == 500
    assert ev.error_type == "ValueError"
    assert ev.error_message == "boom"


def test_route_extracted_when_available():
    events, _, _ = _run(path="/api/users/1", route="/api/users/{id}")
    assert events[0].route == "/api/users/{id}"


def test_route_falls_back_to_none_when_absent():
    events, _, _ = _run(path="/api/users/1", route=None)
    assert events[0].route is None  # collector 侧用 path 兜底


def test_inbound_traceparent_reused():
    tid = "0123456789abcdef0123456789abcdef"
    tp = f"00-{tid}-0123456789abcdef-01"
    headers = [(b"traceparent", tp.encode("latin-1"))]
    events, _, _ = _run(path="/x", headers=headers)
    assert events[0].trace_id == tid


def test_traceparent_built_on_event():
    events, _, _ = _run()
    ev = events[0]
    assert ev.traceparent == f"00-{ev.trace_id}-{ev.span_id}-01"


def test_non_http_scope_passes_through():
    # lifespan / websocket 不应产生事件，直接透传
    fake = _FakeClient()

    async def downstream(scope, receive, send):
        await send({"type": "lifespan.startup.complete"})

    mw = ApiWatchASGIMiddleware(downstream)
    mw._client = fake
    sent = []

    async def receive():
        return {"type": "lifespan.startup"}

    async def send(msg):
        sent.append(msg)

    asyncio.run(mw({"type": "lifespan"}, receive, send))
    assert fake.events == []
