"""Session state: the browsing truth that travels in the workflow JSON (ADR-0002).

The state holds search conditions, loaded result pages (posts included, so
execution and metadata don't re-query the site), cursor, selection, and the
output list. Credentials never appear here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core.errors import StateError
from core.model import Post, SearchConditions


@dataclass
class Page:
    number: int
    posts: list[Post]

    def to_dict(self) -> dict[str, Any]:
        return {"number": self.number, "posts": [p.to_dict() for p in self.posts]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Page":
        return cls(number=int(d["number"]), posts=[Post.from_dict(p) for p in d["posts"]])


@dataclass
class SessionState:
    conditions: SearchConditions | None = None
    pages: list[Page] = field(default_factory=list)
    cursor: int = 0
    selection: int | None = None
    outlist: list[int] = field(default_factory=list)  # 列表模式(T4+);T1 恒空
    page: int = 1  # 当前页(面板翻页位置,随工作流序列化)

    def loaded_posts(self) -> list[Post]:
        return [p for page in self.pages for p in page.posts]

    def post(self, post_id: int) -> Post | None:
        for p in self.loaded_posts():
            if p.id == post_id:
                return p
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "conditions": self.conditions.to_dict() if self.conditions else None,
            "pages": [pg.to_dict() for pg in self.pages],
            "cursor": self.cursor,
            "selection": self.selection,
            "outlist": self.outlist,
            "page": self.page,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SessionState":
        return cls(
            conditions=SearchConditions.from_dict(d["conditions"]) if d.get("conditions") else None,
            pages=[Page.from_dict(pg) for pg in d.get("pages", [])],
            cursor=int(d.get("cursor", 0)),
            selection=d.get("selection"),
            outlist=list(d.get("outlist", [])),
            page=int(d.get("page", 1)),
        )


def session_to_json(state: SessionState) -> str:
    return json.dumps(state.to_dict(), ensure_ascii=False)


def session_from_json(s: str) -> SessionState:
    """Parse workflow widget JSON; empty/blank is a fresh empty session."""
    if not isinstance(s, str) or not s.strip():
        return SessionState()
    try:
        d = json.loads(s)
        if not isinstance(d, dict):
            raise ValueError("session must be a JSON object")
        return SessionState.from_dict(d)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as e:
        raise StateError(
            f"会话状态损坏: {e} — 请清空节点 session 输入框或重新添加节点"
        ) from e
