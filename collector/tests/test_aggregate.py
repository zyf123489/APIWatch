"""聚合计算测试（纯函数）。"""

from apiwatch_collector.aggregate import (
    build_apis,
    build_summary,
    is_error,
    percentile,
)


def _row(route, path, duration_ms, status_code=200, error_type=None):
    return {
        "route": route,
        "path": path,
        "duration_ms": duration_ms,
        "status_code": status_code,
        "error_type": error_type,
    }


# --- percentile ---

def test_percentile_empty():
    assert percentile([], 95) == 0.0


def test_percentile_single():
    assert percentile([42.0], 95) == 42.0


def test_percentile_multi():
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    # 最近秩：ceil(0.95*10)=10 → 第 10 个 = 10
    assert percentile(values, 95) == 10.0


def test_percentile_p50():
    values = [10, 20, 30, 40]
    # ceil(0.5*4)=2 → 第 2 个 = 20
    assert percentile(values, 50) == 20.0


# --- is_error ---

def test_is_error_5xx():
    assert is_error(500, None) is True
    assert is_error(503, None) is True


def test_is_error_with_error_type():
    assert is_error(200, "ValueError") is True


def test_is_error_2xx_4xx_ok():
    assert is_error(200, None) is False
    assert is_error(404, None) is False


# --- build_summary ---

def test_build_summary_empty():
    s = build_summary([])
    assert s["total_requests"] == 0
    assert s["avg_duration_ms"] == 0.0
    assert s["error_rate"] == 0.0


def test_build_summary_basic():
    rows = [
        _row("/a", "/a", 10.0, 200),
        _row("/a", "/a", 20.0, 200),
        _row("/b", "/b", 30.0, 500),
    ]
    s = build_summary(rows)
    assert s["total_requests"] == 3
    assert s["avg_duration_ms"] == 20.0
    assert s["error_count"] == 1
    assert s["error_rate"] == round(1 / 3, 4)


# --- build_apis ---

def test_build_apis_groups_by_route():
    rows = [
        _row("/api/users/{id}", "/api/users/1", 10.0, 200),
        _row("/api/users/{id}", "/api/users/2", 30.0, 200),
        _row("/api/items", "/api/items", 5.0, 500),
    ]
    out = build_apis(rows)
    apis = {a["route"]: a for a in out["apis"]}
    assert apis["/api/users/{id}"]["count"] == 2
    assert apis["/api/users/{id}"]["avg_ms"] == 20.0
    assert apis["/api/items"]["error_count"] == 1
    assert apis["/api/items"]["error_rate"] == 1.0


def test_build_apis_falls_back_to_path_when_no_route():
    rows = [_row(None, "/raw/path", 10.0, 200)]
    out = build_apis(rows)
    assert out["apis"][0]["path"] == "/raw/path"
    assert out["apis"][0]["route"] is None


def test_build_apis_sorted_by_avg_desc():
    rows = [
        _row("/fast", "/fast", 5.0, 200),
        _row("/slow", "/slow", 100.0, 200),
    ]
    out = build_apis(rows)
    assert out["apis"][0]["route"] == "/slow"  # 慢接口在前
