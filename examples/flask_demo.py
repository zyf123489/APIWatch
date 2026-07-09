"""APIWatch Flask 端到端验证示例。

运行前先启动 collector：

    apiwatch start

再启动本示例：

    python examples/flask_demo.py
"""

from __future__ import annotations

import time

from flask import Flask, jsonify

from apiwatch.integrations.flask import ApiWatchFlask

app = Flask(__name__)
ApiWatchFlask(app, project="flask-demo")


@app.get("/")
def index():
    return jsonify(
        {"service": "apiwatch-flask-demo", "try": ["/api/users/1", "/api/slow", "/api/boom"]}
    )


@app.get("/api/users/<int:user_id>")
def get_user(user_id: int):
    return jsonify({"id": user_id, "name": f"user-{user_id}"})


@app.get("/api/slow")
def slow():
    time.sleep(0.3)
    return jsonify({"ok": True, "note": "this endpoint is intentionally slow"})


@app.get("/api/boom")
def boom():
    raise ValueError("intentional demo error")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8081, debug=False)
