"""The core seam: Browser.next_output and the Session handle.

These tests cross the Browser facade with a fake Site adapter (fake HTTP), per
ADR-0003 — the interface is the test surface.
"""

from __future__ import annotations

import pytest

from core.browser import Browser
from core.errors import StateError
from core.model import OutputKind, SearchConditions
from core.session import Page, SessionState, session_to_json
from sites.danbooru import DanbooruSite

from fakes import FakeHttp, IMAGE_BYTES, MemoryCache, make_post


def build_browser(http: FakeHttp, cache=None) -> Browser:
    return Browser(sites={"danbooru": DanbooruSite(http)}, image_cache=cache)


def state_with_selection(http: FakeHttp, selection: int | None = 2) -> str:
    posts = [make_post(1), make_post(2, tags=("2girls", "hug"))]
    state = SessionState(
        conditions=SearchConditions(site="danbooru"),
        pages=[Page(number=1, posts=posts)],
        selection=selection,
    )
    http.bytes_responses[posts[1].file_url] = IMAGE_BYTES
    return session_to_json(state)


class TestManualOutput:
    def test_unbrowsed_state_outputs_empty(self):
        output, state = build_browser(FakeHttp()).next_output("")
        assert output.kind is OutputKind.EMPTY
        assert output.image is None
        assert output.reason  # 明确错误提示
        assert state == ""  # 状态不变

    def test_no_selection_outputs_empty(self):
        http = FakeHttp()
        output, _ = build_browser(http).next_output(state_with_selection(http, selection=None))
        assert output.kind is OutputKind.EMPTY
        assert output.reason

    def test_selected_post_outputs_image_prompt_metadata(self):
        http = FakeHttp()
        browser = build_browser(http)
        output, state = browser.next_output(state_with_selection(http, selection=2))
        assert output.kind is OutputKind.IMAGE
        assert output.image == IMAGE_BYTES
        assert output.prompt == "2girls, hug"  # 提示词 = 标签拼接
        meta = output.metadata
        assert meta["site"] == "danbooru"
        assert meta["post_id"] == 2
        assert meta["file_url"] == "https://cdn.example/2.jpg"
        assert meta["tags"] == ["2girls", "hug"]
        assert meta["rating"] == "g"
        assert meta["score"] == 10
        assert meta["author"] == "artist"
        assert meta["raw"]["id"] == 2  # raw 原始响应
        assert state == state_with_selection(http, selection=2)  # 手动模式重跑输出同一帖子

    def test_animated_post_is_animated_kind(self):
        http = FakeHttp()
        posts = [make_post(1), make_post(2, file_ext="webm", animated=True)]
        state = SessionState(conditions=SearchConditions(site="danbooru"),
                             pages=[Page(1, posts)], selection=2)
        output, _ = build_browser(http).next_output(session_to_json(state))
        assert output.kind is OutputKind.ANIMATED
        assert output.reason and "webm" in output.reason

    def test_download_failure_is_failed_kind(self):
        http = FakeHttp()  # bytes 未提供 → TransportError → FAILED 数据
        posts = [make_post(1), make_post(2, tags=("2girls", "hug"))]
        state = SessionState(conditions=SearchConditions(site="danbooru"),
                             pages=[Page(1, posts)], selection=2)
        output, _ = build_browser(http).next_output(session_to_json(state))
        assert output.kind is OutputKind.FAILED
        assert output.reason and "下载失败" in output.reason

    def test_selection_not_in_loaded_posts_raises_state_error(self):
        http = FakeHttp()
        posts = [make_post(1)]
        state = SessionState(conditions=SearchConditions(site="danbooru"),
                             pages=[Page(1, posts)], selection=999)
        with pytest.raises(StateError):
            build_browser(http).next_output(session_to_json(state))

    def test_unknown_site_raises_state_error(self):
        state = SessionState(conditions=SearchConditions(site="nope"), selection=1)
        with pytest.raises(StateError):
            build_browser(FakeHttp()).next_output(session_to_json(state))

    def test_malformed_state_raises_state_error(self):
        with pytest.raises(StateError):
            build_browser(FakeHttp()).next_output("{broken")

    def test_prompt_derivation_joins_tags_with_comma(self):
        post = make_post(1, tags=("1girl", "long_hair", "blue_eyes"))
        assert build_browser(FakeHttp()).derive_prompt(post) == "1girl, long_hair, blue_eyes"


class TestImageCache:
    def test_cache_serves_second_execution(self):
        http = FakeHttp()
        cache = MemoryCache()
        browser = build_browser(http, cache=cache)
        state = state_with_selection(http, selection=2)
        out1, _ = browser.next_output(state)
        assert out1.kind is OutputKind.IMAGE and out1.image == IMAGE_BYTES
        n_bytes_calls = len(http.bytes_calls)
        out2, _ = browser.next_output(state)
        assert out2.kind is OutputKind.IMAGE
        assert len(http.bytes_calls) == n_bytes_calls  # 第二次命中缓存,不再下载
        assert cache.hits == 1

    def test_cache_absent_still_works(self):
        http = FakeHttp()
        output, _ = build_browser(http).next_output(state_with_selection(http, selection=2))
        assert output.kind is OutputKind.IMAGE


class TestSessionHandle:
    def test_search_fetches_page_one_and_resets(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            dict(make_post(i).raw) for i in (5, 6)
        ]
        browser = build_browser(http)
        session = browser.restore(state_with_selection(http, selection=2))
        result = session.search(SearchConditions(site="danbooru", tags=("blue_eyes",), per_page=40))
        assert [p.id for p in result.posts] == [5, 6]
        new_state = session.serialize()
        state = browser.restore(new_state).state
        assert state.conditions == SearchConditions(site="danbooru", tags=("blue_eyes",), per_page=40)
        assert state.selection is None  # 会话重置:清空选中
        assert state.cursor == 0
        # 重新序列化后往返一致
        assert browser.restore(new_state).state == state

    def test_reopen_same_conditions_keeps_selection(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            dict(make_post(i).raw) for i in (1, 2)
        ]
        browser = build_browser(http)
        session = browser.restore(state_with_selection(http, selection=2))
        session.search(SearchConditions(site="danbooru"))
        assert session.state.selection == 2  # ADR-0002:重开工作流回到同一位置并重拉结果

    def test_reopen_selection_missing_in_fresh_results_cleared(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [dict(make_post(9).raw)]
        browser = build_browser(http)
        session = browser.restore(state_with_selection(http, selection=2))
        session.search(SearchConditions(site="danbooru"))
        assert session.state.selection is None  # 新结果不含原选中 → 清空,不悬挂失效选中

    def test_select_validates_against_loaded_posts(self):
        http = FakeHttp()
        browser = build_browser(http)
        session = browser.restore(state_with_selection(http, selection=2))
        session.select(1)  # 已加载,OK
        assert session.serialize()
        with pytest.raises(StateError):
            browser.restore(state_with_selection(http)).select(999)
