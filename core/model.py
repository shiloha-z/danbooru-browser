"""Domain model: posts, search conditions, and the output value.

All dataclasses are JSON-serializable through explicit to_dict/from_dict
pairs — the session travels in the workflow widget as JSON (ADR-0002).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OutputKind(Enum):
    IMAGE = "image"
    FAILED = "failed"      # 图片下载失败:自动/列表模式跳过,手动模式报错
    ANIMATED = "animated"  # webm/gif/swf:与失败同路径
    EMPTY = "empty"        # 未浏览 / 未选中


@dataclass(frozen=True)
class Post:
    """一张帖子:浏览的数据单元(图 + 元数据),区别于输出的像素 IMAGE。"""

    id: int
    site: str
    file_url: str
    tags: tuple[str, ...] = ()
    rating: str = ""
    score: int = 0
    author: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    animated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "site": self.site,
            "file_url": self.file_url,
            "tags": list(self.tags),
            "rating": self.rating,
            "score": self.score,
            "author": self.author,
            "animated": self.animated,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Post":
        return cls(
            id=int(d["id"]),
            site=d["site"],
            file_url=d.get("file_url", ""),
            tags=tuple(d.get("tags", ())),
            rating=d.get("rating", ""),
            score=int(d.get("score", 0)),
            author=d.get("author", ""),
            raw=d.get("raw", {}),
            animated=bool(d.get("animated", False)),
        )


@dataclass(frozen=True)
class SearchConditions:
    """筛选条件集合:站点 + 标签 + 评级多选 + 排序 + 每页。变更即会话重置。"""

    site: str
    tags: tuple[str, ...] = ()
    exclude_tags: tuple[str, ...] = ()
    ratings: frozenset[str] = frozenset({"g"})  # 默认普通;用户手动多选
    sort: str = "new"  # new | score | random,站点语义映射
    per_page: int = 40

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "tags": list(self.tags),
            "exclude_tags": list(self.exclude_tags),
            "ratings": sorted(self.ratings),
            "sort": self.sort,
            "per_page": self.per_page,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SearchConditions":
        return cls(
            site=d["site"],
            tags=tuple(d.get("tags", ())),
            exclude_tags=tuple(d.get("exclude_tags", ())),
            ratings=frozenset(d.get("ratings", ("g",))),
            sort=d.get("sort", "new"),
            per_page=int(d.get("per_page", 40)),
        )


@dataclass(frozen=True)
class SearchResult:
    posts: tuple[Post, ...]
    page: int
    has_next: bool


@dataclass(frozen=True)
class Output:
    """节点执行的一次输出。kind 决定执行器如何消费(IMAGE 输出三连,其余按策略处理)。"""

    kind: OutputKind
    post: Post | None = None
    image: bytes | None = None
    prompt: str | None = None
    metadata: dict[str, Any] | None = None
    reason: str | None = None
