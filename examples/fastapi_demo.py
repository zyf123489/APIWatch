"""APIWatch 端到端验证用的最小 FastAPI 项目。

接入一行 ApiWatchASGIMiddleware，提供正常 / 慢 / 报错三类接口，
用于验证探针采集与 collector 看板的完整闭环。

运行前先确保 collector 已启动（另开一个终端）：

    apiwatch start                      # collector 跑在 127.0.0.1:8765

再启动本示例（默认 :8080）：

    python examples/fastapi_demo.py
    # 或： uvicorn examples.fastapi_demo:app --port 8080

然后请求几个接口，再打开 http://127.0.0.1:8765/dashboard 查看：

    curl http://127.0.0.1:8080/api/users/1
    curl http://127.0.0.1:8080/api/slow
    curl http://127.0.0.1:8080/api/boom      # 故意报错
"""

from __future__ import annotations

import time

from fastapi import FastAPI

from apiwatch.integrations.asgi import ApiWatchASGIMiddleware

app = FastAPI(title="APIWatch Demo")

# A 模式（默认）：数据上报到独立 collector，看板在 127.0.0.1:8765/dashboard
app.add_middleware(ApiWatchASGIMiddleware, project="demo", framework="fastapi")

# B 模式（可选）：取消下面这行的注释改为挂载到本应用 :8080/APIWatch
# app.add_middleware(ApiWatchASGIMiddleware, project="demo", framework="fastapi",
#                    mount_dashboard="/APIWatch")


@app.get("/")
def index() -> dict:
    return {"service": "apiwatch-demo", "try": ["/api/users/1", "/api/slow", "/api/boom"]}


@app.get("/api/users/{user_id}")
def get_user(user_id: int) -> dict:
    """正常接口。"""
    return {"id": user_id, "name": f"user-{user_id}"}


@app.get("/api/slow")
def slow() -> dict:
    """慢接口：故意耗时，用于验证慢接口排行与 P95。"""
    time.sleep(0.3)
    return {"ok": True, "note": "this endpoint is intentionally slow"}


@app.get("/api/boom")
def boom() -> dict:
    """报错接口：故意抛异常，用于验证错误采集（status=500 + error_type）。"""
    raise ValueError("intentional demo error")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8080)
