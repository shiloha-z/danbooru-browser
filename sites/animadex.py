"""AnimaDex 角色/画师搜索(公开 API,移植自参考包,issue #25)。

经 HttpAdapter 调用,测试注入 FakeHttp。查询逗号分隔为多关键词,
结果按 slug 合并去重。
"""

from __future__ import annotations

from typing import Any

BASE = "https://animadex.net"
MODES = ("characters", "artists")
SORTS = ("count", "fav_count", "random")
PAGE_SIZE = 36


def search(http, mode: str, query: str = "", page: int = 1, sort: str = "count",
           limit: int = PAGE_SIZE, filters: dict[str, Any] | None = None):
    """角色/画师搜索 → (results[:limit], total)。网络错误返回空。"""
    params: dict[str, Any] = {"q": query.strip(), "page": page, "sort": sort}
    if filters:
        for key, vals in filters.items():
            if vals:
                # API 忽略逗号合并值(实测);筛选 UI 每个 facet 单选,原样传递
                params[key] = vals if isinstance(vals, str) else str(vals)
    try:
        data = http.get_json(f"{BASE}/api/{mode}/search", params=params)
    except Exception:
        return [], 0
    return data.get("results", [])[:limit], data.get("total", 0)


def batch_search(http, mode: str, queries: list[str], page: int = 1, sort: str = "count",
                 limit: int = PAGE_SIZE, filters: dict[str, Any] | None = None):
    """多关键词搜索,结果按 slug 合并去重。"""
    seen: set[str] = set()
    merged: list[dict] = []
    total = 0
    for q in queries:
        q = q.strip()
        if not q:
            continue
        results, query_total = search(http, mode, q, page, sort, limit, filters)
        total += query_total
        for item in results:
            slug = item.get("slug", "")
            if slug and slug not in seen:
                seen.add(slug)
                merged.append(item)
    return merged[:limit], total


def facets(http, mode: str) -> dict:
    """获取分类维度(筛选器候选)。"""
    try:
        data = http.get_json(f"{BASE}/api/{mode}/facets")
    except Exception:
        return {}
    return data.get("facets", {})
