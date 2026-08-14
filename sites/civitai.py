"""Civitai site adapter: model search + image stream (issue #7).

与 booru 的差异:无标签体系(搜索 = 模型名 → modelId);评级映射为
nsfw 过滤(None/Soft/X,单选);提示词取图片内嵌生成参数(meta.prompt);
图片 URL 的 original=true/false 段切换原图/压缩版。
"""

from __future__ import annotations

from typing import Any

from core.errors import StateError
from core.model import Post, SearchConditions, SearchResult
from core.site import Site, SiteCapabilities

from .http import HttpAdapter

_NSFW_MAP = {"g": "None", "s": "Soft", "q": "Soft", "e": "X"}
_NSFW_LEVELS = frozenset(_NSFW_MAP.values())  # {"None", "Soft", "X"}
_SORT_MAP = {"new": "Newest", "score": "Most Reactions", "random": "Newest"}


def parse_post(d: dict[str, Any], site: str = "civitai") -> Post:
    url = d.get("url") or ""
    small = url.replace("original=true", "original=false") if url else ""
    return Post(
        id=int(d["id"]),
        site=site,
        file_url=url,
        preview_url=small,
        sample_url=small,
        tags=tuple(d.get("tags") or ()),
        rating="e" if d.get("nsfw") else "g",
        score=0,
        author="",
        raw=d,
        animated=False,
    )


class CivitaiSite:
    BASE_URL = "https://civitai.com/api/v1"

    capabilities = SiteCapabilities(
        site_name="civitai",
        has_tag_search=False,
        has_exclude_tags=False,
        has_model_search=True,
        multi_rating=False,  # nsfw 参数单选(实测多值 400)
        sort_options=("new", "score"),
        prompt_kind="embedded",
    )

    def __init__(self, http: HttpAdapter):
        self._http = http

    def search(self, conditions: SearchConditions, page: int) -> SearchResult:
        if conditions.model_id is None:
            raise StateError("civitai 需要先选择模型:搜索模型名 → 选择模型")
        mapped = sorted({_NSFW_MAP[r] for r in conditions.ratings})  # s/q 都映射 Soft
        if len(mapped) > 1 and len(mapped) < len(_NSFW_LEVELS):
            raise StateError("civitai nsfw 过滤为单选,请只保留一个评级")
        sort = _SORT_MAP.get(conditions.sort)
        if sort is None:
            raise StateError(f"civitai 不支持排序: {conditions.sort}")
        params = {
            "modelId": conditions.model_id,
            "limit": conditions.per_page,
            "page": page,
            "sort": sort,
        }
        if len(mapped) == 1:  # 全档位 = 不过滤
            params["nsfw"] = mapped[0]
        data = self._http.get_json(f"{self.BASE_URL}/images", params=params)
        posts = tuple(parse_post(d) for d in (data.get("items") or []) if isinstance(d, dict))
        return SearchResult(posts=posts, page=page, has_next=len(posts) >= conditions.per_page)

    def search_models(self, query: str, limit: int = 10) -> list[dict]:
        """模型名搜索:面板选择器候选。"""
        data = self._http.get_json(f"{self.BASE_URL}/models", params={"query": query, "limit": limit})
        return [{"id": m["id"], "name": m["name"]} for m in (data.get("items") or [])]

    def fetch_image(self, post: Post, url: str | None = None) -> bytes:
        return self._http.get_bytes(url or post.file_url)
