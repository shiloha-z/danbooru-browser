"""The Site port: what differs across danbooru / gelbooru / civitai.

Sites implement search + image fetch; differences the caller must respect are
declared as data in SiteCapabilities, so core and UI branch on capability
values, never on site identity (ADR-0003).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.model import Post, SearchConditions, SearchResult


@dataclass(frozen=True)
class SiteCapabilities:
    site_name: str
    has_tag_search: bool = True
    has_exclude_tags: bool = True
    has_ratings: bool = True
    has_tag_autocomplete: bool = False  # 面板搜索框标签补全(danbooru 有 /autocomplete.json)
    ratings: tuple[str, ...] = ("g", "s", "q", "e")
    sort_options: tuple[str, ...] = ("new", "score", "random")
    prompt_kind: str = "tags"  # "tags"(booru 标签拼接) | "embedded"(civitai 内嵌生成参数)


class Site(Protocol):
    capabilities: SiteCapabilities

    def search(self, conditions: SearchConditions, page: int) -> SearchResult: ...

    def fetch_image(self, post: Post) -> bytes: ...
