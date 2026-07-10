"""Run APIWatch preview release checks.

This script is intentionally dependency-light. It uses the repo packages in-place,
runs the existing Python and VSCode tests, then starts an isolated collector and
FastAPI demo in-process to verify the probe -> collector -> dashboard loop.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / ".pytest_tmp"
COLLECTOR_PORT = 18765
DEMO_PORT = 18080


def run(command: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("$ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def python_env() -> dict[str, str]:
    env = os.environ.copy()
    paths = [str(ROOT / "probes" / "python"), str(ROOT / "collector")]
    existing = env.get("PYTHONPATH")
    if existing:
        paths.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def run_python_tests() -> None:
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "probes/python/tests",
            "collector/tests",
            "--basetemp",
            ".pytest_tmp",
            "-p",
            "no:cacheprovider",
        ],
        env=python_env(),
    )


def run_vscode_tests() -> None:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    run([npm, "test"], cwd=ROOT / "vscode-extension")


def get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


def wait_for(url: str, attempts: int = 50) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            get(url)
            return
        except Exception as exc:  # noqa: BLE001 - diagnostic retry loop
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"service not ready: {url}: {last_error}")


def run_e2e() -> None:
    TMP.mkdir(exist_ok=True)
    db_path = TMP / "apiwatch_release_check.db"
    try:
        db_path.unlink()
    except FileNotFoundError:
        pass

    os.environ["APIWATCH_DB"] = str(db_path)
    os.environ["APIWATCH_COLLECTOR_URL"] = f"http://127.0.0.1:{COLLECTOR_PORT}"

    sys.path.insert(0, str(ROOT / "collector"))
    sys.path.insert(0, str(ROOT / "probes" / "python"))
    sys.path.insert(0, str(ROOT))

    import uvicorn
    from apiwatch_collector.app import app as collector_app
    from examples.fastapi_demo import app as demo_app

    servers: list[uvicorn.Server] = []

    def start_server(app, port: int) -> None:
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="critical",
            access_log=False,
        )
        server = uvicorn.Server(config)
        servers.append(server)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

    print("$ release-check e2e", flush=True)
    start_server(collector_app, COLLECTOR_PORT)
    start_server(demo_app, DEMO_PORT)

    try:
        wait_for(f"http://127.0.0.1:{COLLECTOR_PORT}/summary")
        wait_for(f"http://127.0.0.1:{DEMO_PORT}/")

        for path in ["/api/users/1", "/api/slow", "/api/boom"]:
            try:
                get(f"http://127.0.0.1:{DEMO_PORT}{path}")
            except urllib.error.HTTPError as exc:
                if exc.code != 500:
                    raise

        summary = {}
        requests = {}
        for _ in range(50):
            _, summary_body = get(
                f"http://127.0.0.1:{COLLECTOR_PORT}/summary"
                "?project=demo&framework=fastapi"
            )
            summary = json.loads(summary_body)
            _, requests_body = get(
                f"http://127.0.0.1:{COLLECTOR_PORT}/requests"
                "?project=demo&framework=fastapi"
            )
            requests = json.loads(requests_body)
            if summary.get("total_requests", 0) >= 3 and summary.get("error_count", 0) >= 1:
                break
            time.sleep(0.1)

        _, filters_body = get(f"http://127.0.0.1:{COLLECTOR_PORT}/filters")
        filters = json.loads(filters_body)
        _, dashboard_body = get(f"http://127.0.0.1:{COLLECTOR_PORT}/dashboard")

        result = {
            "summary": summary,
            "request_total": requests.get("total"),
            "filters": filters,
            "dashboard_contains_apiwatch": "APIWatch" in dashboard_body,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)

        assert summary["total_requests"] >= 3
        assert summary["error_count"] >= 1
        assert requests["total"] >= 3
        assert "demo" in filters["projects"]
        assert "fastapi" in filters["frameworks"]
        assert "APIWatch" in dashboard_body
    finally:
        for server in servers:
            server.should_exit = True
        time.sleep(0.3)


def main() -> int:
    run_python_tests()
    run_vscode_tests()
    run_e2e()
    print("release check passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
