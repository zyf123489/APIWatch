"""SQLite 存储层。

标准库 sqlite3，单表 events。为配合 FastAPI 同步端点在线程池中执行，
连接使用 check_same_thread=False 并以 Lock 串行化访问，保证多线程安全。
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# 与 spec/event.schema.json 对应的列（received_at 为 collector 侧接收时间）
_COLUMNS = [
    "schema_version",
    "project",
    "framework",
    "method",
    "path",
    "route",
    "status_code",
    "duration_ms",
    "trace_id",
    "span_id",
    "traceparent",
    "timestamp",
    "error_type",
    "error_message",
]

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_version TEXT,
    project TEXT,
    framework TEXT,
    method TEXT,
    path TEXT,
    route TEXT,
    status_code INTEGER,
    duration_ms REAL,
    trace_id TEXT,
    span_id TEXT,
    traceparent TEXT,
    timestamp TEXT,
    error_type TEXT,
    error_message TEXT,
    received_at TEXT
);
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_events_route ON events(route);",
    "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_events_status ON events(status_code);",
    "CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id);",
]

# 用于 summary / apis 聚合的精简列
_AGG_SQL = "SELECT route, path, duration_ms, status_code, error_type FROM events"


class Storage:
    """events 表的存储与查询。"""

    def __init__(self, db_path: str = "apiwatch.db") -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute(_CREATE_SQL)
            for stmt in _INDEXES:
                self._conn.execute(stmt)
            self._conn.commit()

    def insert_events(self, events: List[Dict[str, Any]]) -> int:
        """批量写入事件，返回写入条数。缺失字段以 None 兜底。"""
        if not events:
            return 0
        received_at = datetime.now(timezone.utc).isoformat()
        cols = _COLUMNS + ["received_at"]
        placeholders = ", ".join(["?"] * len(cols))
        sql = f"INSERT INTO events ({', '.join(cols)}) VALUES ({placeholders})"
        rows = [
            tuple(ev.get(c) for c in _COLUMNS) + (received_at,) for ev in events
        ]
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()
        return len(rows)

    @staticmethod
    def _filters_sql(
        project: Optional[str] = None, framework: Optional[str] = None
    ) -> tuple[str, list[str]]:
        clauses = []
        params = []
        if project:
            clauses.append("project = ?")
            params.append(project)
        if framework:
            clauses.append("framework = ?")
            params.append(framework)
        if not clauses:
            return "", params
        return " WHERE " + " AND ".join(clauses), params

    def fetch_agg_rows(
        self, project: Optional[str] = None, framework: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """拉取用于 summary / apis 聚合的精简列。"""
        where, params = self._filters_sql(project, framework)
        with self._lock:
            cur = self._conn.execute(_AGG_SQL + where, params)
            return [dict(r) for r in cur.fetchall()]

    def total_count(
        self, project: Optional[str] = None, framework: Optional[str] = None
    ) -> int:
        where, params = self._filters_sql(project, framework)
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) AS c FROM events" + where, params)
            return int(cur.fetchone()["c"])

    def recent(
        self,
        limit: int = 50,
        offset: int = 0,
        project: Optional[str] = None,
        framework: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """按 id 倒序取最近请求。"""
        where, params = self._filters_sql(project, framework)
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM events" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            )
            return [dict(r) for r in cur.fetchall()]

    def distinct_values(self, column: str) -> List[str]:
        """返回 project/framework 的可选值。"""
        if column not in {"project", "framework"}:
            raise ValueError("unsupported distinct column")
        with self._lock:
            cur = self._conn.execute(
                f"SELECT DISTINCT {column} AS value FROM events "
                f"WHERE {column} IS NOT NULL AND {column} != '' ORDER BY {column}"
            )
            return [str(r["value"]) for r in cur.fetchall()]

    def clear_events(self, project: Optional[str] = None) -> int:
        """清空事件。project 为空时清空全部，返回删除条数。"""
        with self._lock:
            if project:
                before = self._conn.total_changes
                self._conn.execute("DELETE FROM events WHERE project = ?", (project,))
                self._conn.commit()
                return self._conn.total_changes - before
            cur = self._conn.execute("SELECT COUNT(*) AS c FROM events")
            count = int(cur.fetchone()["c"])
            self._conn.execute("DELETE FROM events")
            self._conn.commit()
            return count

    def by_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        """按 trace_id 查询（第一版通常一条，为未来多 span 预留列表返回）。"""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM events WHERE trace_id = ? ORDER BY id ASC",
                (trace_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
