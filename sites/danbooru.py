"""Danbooru site adapter: posts.json search + file download."""

from __future__ import annotations

import re
import secrets
from typing import Any

from core.errors import TransportError
from core.model import Post, SearchConditions, SearchResult
from core.site import Site, SiteCapabilities

from .credentials import get_credentials
from .http import HttpAdapter


def parse_post(d: dict[str, Any], site: str) -> Post:
    file_ext = d.get("file_ext", "")
    artist = d.get("tag_string_artist", "")
    return Post(
        id=int(d["id"]),
        site=site,
        file_url=d.get("file_url") or d.get("large_file_url") or "",
        preview_url=d.get("preview_file_url") or d.get("large_file_url") or "",
        sample_url=d.get("large_file_url") or "",
        tags=tuple((d.get("tag_string") or "").split()),
        rating=d.get("rating", ""),
        score=int(d.get("score", 0) or 0),
        author=" ".join(artist.split()),
        raw=d,
        animated=file_ext in ("webm", "gif", "swf", "mp4"),
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
            selected = [r for r in all_ratings if r in conditions.ratings]
            if len(selected) == 1:
                tags.append(f"rating:{selected[0]}")
            elif len(selected) > 1:
                # danbooru 的 ~ OR 只匹配第一个评级(2026-08 实测,其余评级全丢);
                # 必须排除未选评级(-rating: 元标签负数不触发 422)
                tags += [f"-rating:{r}" for r in all_ratings if r not in conditions.ratings]
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
        if conditions.hide_videos:
            tags.append("-video")  # danbooru 的 video 标签覆盖视频帖(实测)
        url = f"{self.BASE_URL}/posts.json"
        params = {"page": page, "limit": conditions.per_page, "tags": " ".join(tags)}
        auth = self._auth()
        try:
            data = self._http.get_json(url, params=params, auth=auth)
        except TransportError as e:
            if e.status == 500 and conditions.sort == "score" and "order:score" in tags:
                # danbooru 对含普通标签的 order:score 查询稳定 500(2026-08 实测);
                # 降级 order:rank(评分/时间混合),最接近评分序且可用的排序
                params = {**params, "tags": params["tags"].replace("order:score", "order:rank")}
                data = self._http.get_json(url, params=params, auth=auth)
            elif e.status == 422 and any(t.startswith("-") and not t.startswith("-rating:")
                                         for t in params["tags"].split()):
                # danbooru 422 组合(2026-08 实测):单普通负标签+order,或多个普通负标签
                # (评级负数 -rating: 不触发)。重试:去掉 order,只保留第一个普通负标签,
                # 其余普通负标签客户端过滤;评级负数保留在查询里
                tokens = params["tags"].split()
                regular_negs = [t for t in tokens if t.startswith("-") and not t.startswith("-rating:")]
                rating_negs = [t for t in tokens if t.startswith("-rating:")]
                kept = [t for t in tokens
                        if (not t.startswith("-") or t in regular_negs[:1] + rating_negs)
                        and not t.startswith("order:")]
                data = self._http.get_json(
                    url, params={**params, "tags": " ".join(kept)}, auth=auth,
                )
                data = [d for d in data if not self._matches_negatives(d, regular_negs[1:])]
            else:
                raise
        posts = tuple(parse_post(d, "danbooru") for d in data)
        if conditions.hide_videos:
            # -video 标签覆盖绝大多数视频帖;客户端再按 animated 兜底
            # (gif 动画、缺标签的视频帖;分页计数按过滤后算,可接受偏差)
            posts = tuple(p for p in posts if not p.animated)
        return SearchResult(posts=posts, page=page, has_next=len(posts) >= conditions.per_page)

    @staticmethod
    def _matches_negatives(d: dict[str, Any], negatives: list[str]) -> bool:
        """客户端负标签过滤:多负标签 422 降级时,其余负标签按 tag_string 匹配。"""
        if not negatives:
            return False
        tag_set = set((d.get("tag_string") or "").split())
        return any(neg[1:] in tag_set for neg in negatives)

    def _auth(self) -> tuple[str, str] | None:
        """danbooru 可选基本认证(login/api_key);未配置则匿名(限速但可用)。"""
        creds = get_credentials("danbooru") or {}
        if creds.get("login") and creds.get("api_key"):
            return (str(creds["login"]), str(creds["api_key"]))
        return None

    def fetch_image(self, post: Post, url: str | None = None) -> bytes:
        return self._http.get_bytes(url or post.file_url)

    def autocomplete_tags(self, query: str, limit: int = 10) -> list[str]:
        """标签补全:面板搜索框输入时的候选列表(站点能力,gelbooru/civitai 后续)。"""
        data = self._http.get_json(
            f"{self.BASE_URL}/autocomplete.json",
            params={"search[query]": query, "search[type]": "tag_query", "limit": limit},
        )
        return [d["value"] for d in data if isinstance(d, dict) and d.get("value")]
