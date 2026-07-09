"""聚合计算。

基于 storage 拉取的精简行，在 Python 侧计算 summary 与按接口的统计。
第一版本地开发态数据量小，内存聚合最简单且不易出错。

错误判定：status_code >= 500 或 error_type 非空视为错误（聚焦服务端问题）。
接口分组键：优先 route（路由模板），采集不到时用 path 兜底。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def is_error(status_code: Optional[int], error_type: Optional[str]) -> bool:
    """判定一条请求是否算错误。"""
    if error_type:
        return True
    return status_code is not None and status_code >= 500


def percentile(values: List[float], p: float) -> float:
    """最近秩法计算百分位（p 取 0~100）。空列表返回 0。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    # 最近秩：rank = ceil(p/100 * N)，取第 rank 个（1-based）
    import math

    rank = max(1, math.ceil(p / 100.0 * len(ordered)))
    rank = min(rank, len(ordered))
    return float(ordered[rank - 1])


def build_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """全局汇总：总请求数、平均耗时、P95、错误率。"""
    total = len(rows)
    if total == 0:
        return {
            "total_requests": 0,
            "avg_duration_ms": 0.0,
            "p95_duration_ms": 0.0,
            "error_rate": 0.0,
            "error_count": 0,
        }
    durations = [float(r.get("duration_ms") or 0.0) for r in rows]
    error_count = sum(
        1 for r in rows if is_error(r.get("status_code"), r.get("error_type"))
    )
    return {
        "total_requests": total,
        "avg_duration_ms": round(sum(durations) / total, 3),
        "p95_duration_ms": round(percentile(durations, 95), 3),
        "error_rate": round(error_count / total, 4),
        "error_count": error_count,
    }


def build_apis(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按接口（route 兜底 path）聚合：count / avg / p95 / max / 错误率。"""
    groups: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        route = r.get("route")
        path = r.get("path") or ""
        key = route or path
        g = groups.get(key)
        if g is None:
            g = {
                "route": route,
                "path": path,
                "durations": [],
                "error_count": 0,
            }
            groups[key] = g
        g["durations"].append(float(r.get("duration_ms") or 0.0))
        if is_error(r.get("status_code"), r.get("error_type")):
            g["error_count"] += 1

    apis: List[Dict[str, Any]] = []
    for g in groups.values():
        durations = g["durations"]
        count = len(durations)
        apis.append(
            {
                "route": g["route"],
                "path": g["path"],
                "count": count,
                "avg_ms": round(sum(durations) / count, 3) if count else 0.0,
                "p95_ms": round(percentile(durations, 95), 3),
                "max_ms": round(max(durations), 3) if durations else 0.0,
                "error_count": g["error_count"],
                "error_rate": round(g["error_count"] / count, 4) if count else 0.0,
            }
        )
    # 默认按平均耗时降序，便于看板直接呈现慢接口在前
    apis.sort(key=lambda a: a["avg_ms"], reverse=True)
    return {"apis": apis}
