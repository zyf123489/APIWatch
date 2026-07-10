"""APIWatch collector 命令行入口。

    apiwatch start [--host 127.0.0.1] [--port 8765] [--db apiwatch.db]
    apiwatch stop

第一版 stop 仅作占位提示（前台运行时用 Ctrl-C 停止）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _is_loopback_host(host: str) -> bool:
    return host.strip().lower() in _LOOPBACK_HOSTS


def _validate_token(token: str | None) -> str | None:
    if token is None:
        return None
    value = token.strip()
    if not value:
        return None
    if len(value) < 32:
        raise ValueError("APIWATCH token must contain at least 32 characters")
    return value


def _cmd_start(args: argparse.Namespace) -> int:
    try:
        token = _validate_token(args.token)
    except ValueError as exc:
        print(f"APIWatch collector 未启动：{exc}")
        return 2
    if not _is_loopback_host(args.host) and token is None:
        print("APIWatch collector 未启动：非回环 host 必须通过 --token 或 APIWATCH_TOKEN 配置访问 token。")
        return 2

    # 让 app 模块在导入时读取到正确的 DB 路径
    os.environ["APIWATCH_DB"] = args.db
    if token is not None:
        os.environ["APIWATCH_TOKEN"] = token
    else:
        os.environ.pop("APIWATCH_TOKEN", None)

    import uvicorn

    print(f"APIWatch collector 启动中 → http://{args.host}:{args.port}")
    print(f"看板：http://{args.host}:{args.port}/dashboard")
    print(f"数据库：{os.path.abspath(args.db)}")
    print("按 Ctrl-C 停止。")
    uvicorn.run(
        "apiwatch_collector.app:app",
        host=args.host,
        port=args.port,
        log_level="warning",
    )
    return 0


def _cmd_stop(_: argparse.Namespace) -> int:
    print("前台运行的 collector 请用 Ctrl-C 停止。")
    print("（后台进程管理将在后续版本随 VSCode 插件一并提供。）")
    return 0


def _base_url(args: argparse.Namespace) -> str:
    return (args.url or f"http://{args.host}:{args.port}").rstrip("/")


def _request_json(
    url: str, method: str = "GET", token: str | None = None
) -> tuple[int, dict | None, str | None]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else None
            return resp.status, data, None
    except urllib.error.HTTPError as exc:
        return exc.code, None, str(exc)
    except (urllib.error.URLError, OSError) as exc:
        return 0, None, str(exc)


def _cmd_doctor(args: argparse.Namespace) -> int:
    base = _base_url(args)
    print(f"APIWatch doctor")
    print(f"collector: {base}")
    status, summary, error = _request_json(f"{base}/summary", token=args.token)
    if status == 200 and summary is not None:
        print("collector: OK")
        print(f"dashboard: {base}/dashboard")
        print(f"requests: {summary.get('total_requests', 0)}")
        return 0
    print("collector: unavailable")
    print(f"error: {error or status}")
    print("hint: run `apiwatch start` in another terminal.")
    return 1


def _cmd_clear(args: argparse.Namespace) -> int:
    base = _base_url(args)
    url = f"{base}/events"
    if args.project:
        url += "?project=" + urllib.parse.quote(args.project)
    status, body, error = _request_json(url, method="DELETE", token=args.token)
    if status == 200 and body is not None:
        project = body.get("project") or "all"
        print(f"cleared: {body.get('deleted', 0)} events (project={project})")
        return 0
    print("clear failed")
    print(f"collector: {base}")
    print(f"error: {error or status}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apiwatch", description="APIWatch 本地 API 观测 collector"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="启动本地 collector 服务")
    start.add_argument("--host", default="127.0.0.1")
    start.add_argument("--port", type=int, default=8765)
    start.add_argument("--db", default="apiwatch.db", help="SQLite 文件路径")
    start.add_argument(
        "--token",
        default=os.environ.get("APIWATCH_TOKEN"),
        help="远程绑定必需的访问 token（也可使用 APIWATCH_TOKEN）",
    )
    start.set_defaults(func=_cmd_start)

    stop = sub.add_parser("stop", help="停止 collector（占位）")
    stop.set_defaults(func=_cmd_stop)

    doctor = sub.add_parser("doctor", help="检查本地 collector 状态")
    doctor.add_argument("--host", default="127.0.0.1")
    doctor.add_argument("--port", type=int, default=8765)
    doctor.add_argument("--url", default=None, help="collector 基地址")
    doctor.add_argument(
        "--token", default=os.environ.get("APIWATCH_TOKEN"), help="collector 访问 token"
    )
    doctor.set_defaults(func=_cmd_doctor)

    clear = sub.add_parser("clear", help="清空 collector 中的事件数据")
    clear.add_argument("--host", default="127.0.0.1")
    clear.add_argument("--port", type=int, default=8765)
    clear.add_argument("--url", default=None, help="collector 基地址")
    clear.add_argument("--project", default=None, help="只清空指定 project")
    clear.add_argument(
        "--token", default=os.environ.get("APIWATCH_TOKEN"), help="collector 访问 token"
    )
    clear.set_defaults(func=_cmd_clear)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
