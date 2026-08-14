"""Danbooru site adapter: posts.json search + file download."""

from __future__ import annotations

import secrets
from typing import Any

from core.errors import TransportError
from core.model import Post, SearchConditions, SearchResult
from core.site import Site, SiteCapabilities

from .http import HttpAdapter


def parse_post(d: dict[str, Any], site: str) -> Post:
    file_ext = d.get("file_ext", "")
    artist = d.get("tag_string_artist", "")
    return Post(
        id=int(d["id"]),
        site=site,
        file_url=d.get("file_url") or d.get("large_file_url") or "",
        tags=tuple((d.get("tag_string") or "").split()),
        rating=d.get("rating", ""),
        score=int(d.get("score", 0) or 0),
        author=" ".join(artist.split()),
        raw=d,
        animated=file_ext in ("webm", "gif", "swf"),
    )


class DanbooruSite:
    BASE_URL = "https://danbooru.donmai.us"

    capabilities = SiteCapabilities(site_name="danbooru", has_tag_autocomplete=True)

    def __init__(self, http: HttpAdapter):
        self._http = http

    def search(self, conditions: SearchConditions, page: int) -> SearchResult:
        all_ratings = self.capabilities.ratings  # 能力表是唯一来源(ADR-0003)
        tags = list(conditions.tags)
        if conditions.ratings != frozenset(all_ratings):
            # danbooru 空格分隔是 AND,多选评级必须用 ~(OR)连接,否则必然空结果
            selected = [f"rating:{r}" for r in all_ratings if r in conditions.ratings]
            if selected:
                tags.append("~".join(selected))
        if conditions.sort == "score":
            tags.append("order:score")
        elif conditions.sort == "random":
            # danbooru API 裸 order:random 目前 500(2026-08 实测);带 seed 的
            # order:random:NN 正常返回(API 修复随机前退化为默认序)。每次搜索
            # 生成新 seed,保证各次搜索结果不同。
            tags.append(f"order:random:{secrets.randbelow(2**31)}")
        elif conditions.sort == "new":
            # 显式映射最新:danbooru 默认排序可能随配置变;注意 order:id 是升序(旧帖优先),
            # 新帖优先必须用 order:id_desc(2026-08 实测)
            tags.append("order:id_desc")
        tags += [f"-{t}" for t in conditions.exclude_tags]
        url = f"{self.BASE_URL}/posts.json"
        params = {"page": page, "limit": conditions.per_page, "tags": " ".join(tags)}
        try:
            data = self._http.get_json(url, params=params)
        except TransportError as e:
            if conditions.sort != "score" or "order:score" not in tags or e.status != 500:
                raise
            # danbooru 对含普通标签的 order:score 查询稳定 500(2026-08 实测);
            # 降级 order:rank(评分/时间混合),最接近评分序且可用的排序
            params = {**params, "tags": params["tags"].replace("order:score", "order:rank")}
            data = self._http.get_json(url, params=params)
        posts = tuple(parse_post(d, "danbooru") for d in data)
        return SearchResult(posts=posts, page=page, has_next=len(posts) >= conditions.per_page)

    def fetch_image(self, post: Post) -> bytes:
        return self._http.get_bytes(post.file_url)

    def autocomplete_tags(self, query: str, limit: int = 10) -> list[str]:
        """标签补全:面板搜索框输入时的候选列表(站点能力,gelbooru/civitai 后续)。"""
        data = self._http.get_json(
            f"{self.BASE_URL}/autocomplete.json",
            params={"search[query]": query, "search[type]": "tag_query", "limit": limit},
        )
        return [d["value"] for d in data if isinstance(d, dict) and d.get("value")]
