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

    def next_output(self, state_json: str, prefer_original: bool = False) -> tuple[Output, str]:
        """解析会话 → 按模式推进 → 输出。手动模式不改状态;自动模式返回推进后的状态。"""
        state = session_from_json(state_json)
        if state.conditions is None:
            return Output(OutputKind.EMPTY, reason="未浏览:先在面板中浏览并选中一张帖子"), state_json
        if state.mode == "auto":
            output, new_state = self._auto_output(state, prefer_original)
            return output, session_to_json(new_state)
        if state.mode == "list":
            output, new_state = self._list_output(state, prefer_original)
            return output, session_to_json(new_state)
        if not state.loaded_posts():
            return Output(OutputKind.EMPTY, reason="结果为空:当前筛选条件没有帖子"), state_json
        if state.selection is None:
            return Output(OutputKind.EMPTY, reason="未选中帖子:在面板中点击一张帖子后执行"), state_json
        post = self.require_loaded(state, state.selection, "(工作流可能被编辑);请在面板中重新浏览")
        return self._post_output(state, post, prefer_original), state_json

    def _post_output(self, state: SessionState, post: Post, prefer_original: bool = False) -> Output:
        """取图 → 派生提示词 → 组装输出(手动与自动共用尾部)。"""
        site = self.site(state.conditions.site)
        if post.animated:
            return Output(OutputKind.ANIMATED, post=post,
                          reason="帖子是动画(webm/gif),暂不支持输出")
        try:
            image = self._fetch_image(site, post, prefer_original)
        except TransportError as e:
            url = post.file_url if prefer_original else (post.sample_url or post.file_url)
            return Output(OutputKind.FAILED, post=post, reason=f"下载失败: {url} ({e})")
        return Output(
            OutputKind.IMAGE, post=post, image=image,
            prompt=self.derive_prompt(post, state.out_filter), metadata=build_metadata(post),
        )

    def _list_output(self, state: SessionState, prefer_original: bool = False) -> tuple[Output, SessionState]:
        """列表模式:输出列表中下一张 → 游标 +1,末尾回绕无限循环;失败/动画帖跳过并标红(T9)。"""
        if not state.outlist:
            return Output(OutputKind.EMPTY, reason="列表为空:先在面板中加入帖子"), state
        cap = len(state.outlist) + 1  # 一整圈:全失败时给出明确报错而非无限循环
        for _ in range(cap):
            if state.cursor < 0 or state.cursor >= len(state.outlist):
                state.cursor = 0  # 无限循环
            post_id = state.outlist[state.cursor]
            state.cursor += 1
            post = state.post(post_id)
            if post is None:
                self._mark_failed(state, post_id)
                continue  # 不在已加载结果:按失败跳过
            output = self._post_output(state, post, prefer_original)
            if output.kind is OutputKind.IMAGE:
                return output, state
            self._mark_failed(state, post_id)
        return Output(OutputKind.EMPTY, reason="列表中连续多张失败,请移除失败项"), state

    @staticmethod
    def _mark_failed(state: SessionState, post_id: int) -> None:
        if post_id not in state.failed:
            state.failed.append(post_id)

    def _auto_output(self, state: SessionState, prefer_original: bool = False) -> tuple[Output, SessionState]:
        """自动模式:输出游标帖 → 游标 +1;失败/动画帖跳过并标红,继续下一张(T9)。"""
        if state.cursor < 0:  # 防御篡改的会话 JSON
            state.cursor = 0
        posts = state.loaded_posts()
        fetches = 0
        while True:
            while state.cursor >= len(posts):
                fetches += 1
                if fetches > 5:  # 防御性上限:站点忽略页码时避免疯狂拉取
                    return Output(OutputKind.EMPTY, reason="已到结果末尾"), state
                next_page = max((pg.number for pg in state.pages), default=0) + 1
                site = self.site(state.conditions.site)
                try:
                    result = site.search(state.conditions, page=next_page)
                except TransportError as e:
                    return Output(OutputKind.FAILED, reason=f"自动模式翻页失败: {e}"), state
                if not result.posts:
                    return Output(OutputKind.EMPTY, reason="已到结果末尾"), state
                state.pages.append(Page(number=next_page, posts=list(result.posts)))
                posts = state.loaded_posts()
            post = posts[state.cursor]
            output = self._post_output(state, post, prefer_original)
            if output.kind is OutputKind.IMAGE:
                state.cursor += 1
                return output, state
            # 失败/动画:跳过并标红,继续下一张
            self._mark_failed(state, post.id)
            state.cursor += 1

    # ---------- 面板操作 ----------

    def restore(self, state_json: str) -> "Session":
        return Session(session_from_json(state_json), self)

    def derive_prompt(self, post: Post, out_filter: tuple[str, ...] = ()) -> str:
        caps = self.site(post.site).capabilities
        if caps.prompt_kind == "tags":
            return ", ".join(t for t in post.tags if t not in out_filter)
        # civitai:内嵌生成参数里的 prompt;缺失 → 空串(面板提示)
        return str((post.raw.get("meta") or {}).get("prompt") or "")

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

    def _fetch_image(self, site: Site, post: Post, prefer_original: bool = False) -> bytes:
        """默认下载大图预览(sample);原图开关下载原图。缓存按下载 URL 键控(T8)。"""
        url = post.file_url if prefer_original else (post.sample_url or post.file_url)
        if self._cache is not None:
            cached = self._cache.get(url)
            if cached is not None:
                return cached
        data = site.fetch_image(post, url)
        if self._cache is not None:
            self._cache.put(url, data)
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
        same_conditions = prev.conditions == conditions
        if not (same_conditions and any(p.id == prev.selection for p in result.posts)):
            prev = SessionState()  # 会话重置:丢弃选中
        self.state = SessionState(
            conditions=conditions,
            pages=[Page(number=1, posts=list(result.posts))],
            # 重开重拉(条件不变)保留游标,与选中门控解耦(自动/列表无选中也推进);
            # 筛选变更归零。cursor 从原 state 取,prev 可能已被替换
            cursor=self.state.cursor if same_conditions else 0,
            selection=prev.selection,
            outlist=self.state.outlist,
            page=1,
            mode=self.state.mode,
            out_filter=self.state.out_filter,
            failed=[],  # 新搜索结果,旧失败标记作废
        )
        return result

    def goto_page(self, page: int) -> SearchResult:
        """按页导航:拉取该页并入 pages;选中项不在新页中则清空(ADR-0002)。"""
        if page < 1:
            raise StateError("页码必须 ≥ 1")
        if self.state.conditions is None:
            raise StateError("未浏览:先在面板中搜索")
        site = self._browser.site(self.state.conditions.site)
        result = site.search(self.state.conditions, page=page)
        kept = self.state.selection if any(p.id == self.state.selection for p in result.posts) else None
        pages = [pg for pg in self.state.pages if pg.number != page]
        if result.posts:  # 空页(跳转越界)不累积,避免会话膨胀;页码仍记录
            pages.append(Page(number=page, posts=list(result.posts)))
            pages.sort(key=lambda pg: pg.number)
        self.state = SessionState(
            conditions=self.state.conditions,
            pages=pages,
            # 同页重拉(重开工作流恢复)保留游标(ADR-0002);翻到不同页归零
            cursor=self.state.cursor if page == self.state.page else 0,
            selection=kept,
            outlist=self.state.outlist,
            page=page,
            mode=self.state.mode,
            out_filter=self.state.out_filter,
            failed=self.state.failed,  # 失败标记跨翻页保留
        )
        return result

    def _post_index(self, post_id: int) -> int | None:
        posts = self.state.loaded_posts()
        for i, p in enumerate(posts):
            if p.id == post_id:
                return i
        return None

    def select(self, post_id: int) -> None:
        """选中一张已加载的帖子;未加载则 StateError。游标同步到该帖(自动模式从这继续)。"""
        self._browser.require_loaded(self.state, post_id)
        self.state.selection = post_id
        if self.state.mode != "list":  # 列表模式的游标是列表位置,与选中无关
            index = self._post_index(post_id)
            if index is not None:
                self.state.cursor = index

    def set_mode(self, mode: str) -> None:
        """切换输出模式;自动游标挪到选中帖,列表游标归零。"""
        if mode not in ("manual", "auto", "list"):
            raise StateError(f"未知模式: {mode}")
        self.state.mode = mode
        if mode == "auto" and self.state.selection is not None:
            index = self._post_index(self.state.selection)
            if index is not None:
                self.state.cursor = index
        elif mode == "list":
            self.state.cursor = 0

    def add_to_list(self, post_id: int) -> None:
        """加入输出列表(去重;仅限已加载帖子)。"""
        self._browser.require_loaded(self.state, post_id)
        if post_id not in self.state.outlist:
            self.state.outlist.append(post_id)

    def insert_to_list(self, post_id: int, index: int) -> None:
        """插入指定位置(去重;index 越界钳制到末尾)。"""
        self._browser.require_loaded(self.state, post_id)
        if post_id in self.state.outlist:
            return
        index = max(0, min(index, len(self.state.outlist)))
        self.state.outlist.insert(index, post_id)

    def remove_from_list(self, post_id: int) -> None:
        if post_id in self.state.outlist:
            self.state.outlist.remove(post_id)

    def clear_list(self) -> None:
        self.state.outlist.clear()

    def set_out_filter(self, tags: tuple[str, ...]) -> None:
        """输出过滤:Prompt 派生剔除的标签(不影响搜索条件与结果)。"""
        self.state.out_filter = tuple(tags)

    def reset_cursor(self) -> None:
        """回到起点:自动模式 = 选中帖;列表模式 = 列表开头;无选中则开头。"""
        if self.state.mode == "list":
            self.state.cursor = 0
            return
        if self.state.selection is not None:
            index = self._post_index(self.state.selection)
            if index is not None:
                self.state.cursor = index
                return
        self.state.cursor = 0

    def serialize(self) -> str:
        return session_to_json(self.state)
