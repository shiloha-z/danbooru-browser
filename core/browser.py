"""The Browser facade — the single test seam (ADR-0003).

- next_output(state_json) -> (Output, state_json): the executor's only entry
  point. A total function: restore, resolve selection, fetch, derive prompt,
  cache, and write back; failure conditions are data, state/transport errors
  raise.
- restore(state_json) -> Session: the panel's handle. Restore → action →
  serialize per request; nothing is held between actions (stateless server
  side — the workflow JSON stays the truth).
"""

from __future__ import annotations

from typing import Mapping, Protocol

from core.errors import StateError, TransportError
from core.model import Output, OutputKind, Post, SearchConditions, SearchResult
from core.session import Page, SessionState, session_from_json, session_to_json
from core.site import Site


class ImageCache(Protocol):
    """Bounded local cache for downloaded images (internal, never exposed)."""

    def get(self, key: str) -> bytes | None: ...

    def put(self, key: str, data: bytes) -> None: ...


def build_metadata(post: Post) -> dict:
    """元数据 JSON:站点、帖子 ID、原图 URL、标签数组、评级、评分、作者、raw。"""
    return {
        "site": post.site,
        "post_id": post.id,
        "file_url": post.file_url,
        "tags": list(post.tags),
        "rating": post.rating,
        "score": post.score,
        "author": post.author,
        "raw": post.raw,
    }


class Browser:
    def __init__(self, sites: Mapping[str, Site], image_cache: ImageCache | None = None):
        self._sites = sites
        self._cache = image_cache

    # ---------- 执行器入口 ----------

    def next_output(self, state_json: str) -> tuple[Output, str]:
        """解析会话 → 解析选中项 → 取图 → 派生提示词 → 输出。手动模式不改状态。"""
        state = session_from_json(state_json)
        if state.conditions is None:
            return Output(OutputKind.EMPTY, reason="未浏览:先在面板中浏览并选中一张帖子"), state_json
        if state.selection is None:
            return Output(OutputKind.EMPTY, reason="未选中帖子:在面板中点击一张帖子后执行"), state_json
        post = self.require_loaded(state, state.selection, "(工作流可能被编辑);请在面板中重新浏览")
        site = self.site(state.conditions.site)
        if post.animated:
            return Output(OutputKind.ANIMATED, post=post,
                          reason="帖子是动画(webm/gif),暂不支持输出"), state_json
        try:
            image = self._fetch_image(site, post)
        except TransportError as e:
            return Output(OutputKind.FAILED, post=post,
                          reason=f"下载失败: {post.file_url} ({e})"), state_json
        return Output(
            OutputKind.IMAGE, post=post, image=image,
            prompt=self.derive_prompt(post), metadata=build_metadata(post),
        ), state_json

    # ---------- 面板操作 ----------

    def restore(self, state_json: str) -> "Session":
        return Session(session_from_json(state_json), self)

    def derive_prompt(self, post: Post) -> str:
        caps = self.site(post.site).capabilities
        if caps.prompt_kind == "tags":
            return ", ".join(post.tags)
        return str(post.raw.get("embedded_prompt", ""))  # civitai:内嵌生成提示词(T2+)

    # ---------- 内部 ----------

    def site(self, name: str) -> Site:
        site = self._sites.get(name)
        if site is None:
            raise StateError(f"未知站点: {name}")
        return site

    def require_loaded(self, state: SessionState, post_id: int, hint: str = "") -> Post:
        """解析选中项;未加载 → StateError。执行器与面板校验共用(ADR-0003)。"""
        post = state.post(post_id)
        if post is None:
            raise StateError(f"帖子 #{post_id} 不在已加载结果中{hint}")
        return post

    def _fetch_image(self, site: Site, post: Post) -> bytes:
        key = f"{post.site}:{post.id}"
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
        data = site.fetch_image(post)
        if self._cache is not None:
            self._cache.put(key, data)
        return data


class Session:
    """面板操作句柄:恢复 → 动作 → 序列化;动作之间不保留状态(ADR-0003)。"""

    def __init__(self, state: SessionState, browser: Browser):
        self.state = state
        self._browser = browser

    def search(self, conditions: SearchConditions) -> SearchResult:
        """首屏搜索(第 1 页)。筛选变更 = 会话重置:清空结果、游标归零、清空选中;
        输出列表保留(显式策展,不因筛选变化而丢)。

        例外:条件不变且新结果仍含原选中项时保留选中——重开工作流回到同一位置并重拉
        结果(ADR-0002),而不是把序列化的选中项当一次性提示丢掉。"""
        site = self._browser.site(conditions.site)
        result = site.search(conditions, page=1)
        prev = self.state
        if not (prev.conditions == conditions and any(p.id == prev.selection for p in result.posts)):
            prev = SessionState()  # 会话重置:丢弃选中
        self.state = SessionState(
            conditions=conditions,
            pages=[Page(number=1, posts=list(result.posts))],
            cursor=0,
            selection=prev.selection,
            outlist=self.state.outlist,
        )
        return result

    def select(self, post_id: int) -> None:
        """选中一张已加载的帖子;未加载则 StateError(校验语义,面板与执行共用)。"""
        self._browser.require_loaded(self.state, post_id)
        self.state.selection = post_id

    def serialize(self) -> str:
        return session_to_json(self.state)
