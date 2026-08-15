"""The core seam: Browser.next_output and the Session handle.

These tests cross the Browser facade with a fake Site adapter (fake HTTP), per
ADR-0003 — the interface is the test surface.
"""

from __future__ import annotations

import pytest

from core.browser import Browser
from core.errors import StateError
from core.model import OutputKind, SearchConditions
from core.session import Page, SessionState, session_from_json, session_to_json
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
    for p in posts:  # 默认下载 sample,原图开关下载 file_url,两个都备
        http.bytes_responses[p.file_url] = IMAGE_BYTES
        http.bytes_responses[p.sample_url] = IMAGE_BYTES
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
        from dataclasses import replace
        post = replace(make_post(1), site="nope")  # 帖子自身站点未知 → 按帖子站点取站时报错
        state = SessionState(conditions=SearchConditions(site="nope"),
                             pages=[Page(1, [post])], selection=1)
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

    def test_exclude_tags_change_triggers_reset(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            dict(make_post(5).raw), dict(make_post(6).raw),
        ]
        browser = build_browser(http)
        session = browser.restore(state_with_selection(http, selection=2))
        session.search(SearchConditions(site="danbooru", exclude_tags=("nude",), per_page=40))
        state = browser.restore(session.serialize()).state
        assert state.conditions.exclude_tags == ("nude",)
        assert state.selection is None  # 排除标签变更 = 筛选变更 → 会话重置

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


class TestAutoMode:
    """自动模式:游标推进、自动翻页、重选重启、重置(issue #8)。"""

    def build_auto_state(self, http, post_ids=(1, 2, 3), selection=None):
        """真实流程:浏览 → 选中 → 点「自动」→ 重置游标(选中不动游标,重置才移)。"""
        posts = [make_post(i) for i in post_ids]
        for p in posts:
            http.bytes_responses[p.file_url] = IMAGE_BYTES
            http.bytes_responses[p.sample_url] = IMAGE_BYTES
        session = build_browser(http).restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(number=1, posts=posts)],
            selection=selection,
        )))
        session.set_mode("auto")
        session.reset_cursor()
        return session.serialize()

    def test_set_mode_auto_does_not_move_cursor(self):
        # 选中只是标记:进入自动不改变游标;重置游标才移到选中帖
        http = FakeHttp()
        browser = build_browser(http)
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(number=1, posts=[make_post(1), make_post(2), make_post(3)])],
            selection=2,
        )))
        session.set_mode("auto")
        assert session.state.mode == "auto"
        assert session.state.cursor == 0  # 游标保持,不跳选中
        session.reset_cursor()
        assert session.state.cursor == 1  # 重置后才到选中帖 2 的索引

    def test_auto_advances_cursor_each_call(self):
        http = FakeHttp()
        browser = build_browser(http)
        state = self.build_auto_state(http, selection=2)
        out1, s1 = browser.next_output(state)
        assert out1.kind is OutputKind.IMAGE and out1.post.id == 2  # 先输出选中帖
        assert browser.restore(s1).state.cursor == 2
        out2, s2 = browser.next_output(s1)
        assert out2.kind is OutputKind.IMAGE and out2.post.id == 3  # 再推进一张
        assert browser.restore(s2).state.cursor == 3

    def test_auto_fetches_next_page_when_cursor_past_end(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            dict(make_post(4).raw), dict(make_post(5).raw),
        ]
        for p in (make_post(4), make_post(5)):
            http.bytes_responses[p.file_url] = IMAGE_BYTES
            http.bytes_responses[p.sample_url] = IMAGE_BYTES
        browser = build_browser(http)
        state = self.build_auto_state(http, selection=3)  # 最后一帖,游标=2
        out, s = browser.next_output(state)
        assert out.kind is OutputKind.IMAGE and out.post.id == 3
        # 游标 3 ≥ 已加载 3 帖 → 自动拉第 2 页
        out2, s2 = browser.next_output(s)
        assert out2.kind is OutputKind.IMAGE and out2.post.id == 4
        new_state = browser.restore(s2).state
        assert new_state.cursor == 4
        assert {pg.number for pg in new_state.pages} == {1, 2}

    def test_auto_empty_page_reports_end(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = []
        browser = build_browser(http)
        state = self.build_auto_state(http, selection=3)
        _, s = browser.next_output(state)  # 输出 3,游标越界
        out, _ = browser.next_output(s)  # 下一页为空 → 末尾
        assert out.kind is OutputKind.EMPTY
        assert "末尾" in (out.reason or "")

    def test_reselect_does_not_move_cursor(self):
        # 重选只是标记;重置游标才把游标移到选中帖
        http = FakeHttp()
        browser = build_browser(http)
        session = browser.restore(self.build_auto_state(http, selection=3))
        session.select(1)  # 重选 1
        assert session.state.cursor == 2  # 游标不动(仍在 3 的索引)
        session.reset_cursor()
        assert session.state.cursor == 0  # 重置后到 1 的索引

    def test_reset_cursor_returns_to_selection(self):
        http = FakeHttp()
        browser = build_browser(http)
        session = browser.restore(self.build_auto_state(http, selection=2))
        session.reset_cursor()
        assert session.state.cursor == 1

    def test_mode_serializes_and_defaults_manual(self):
        assert session_from_json('{"conditions": null, "pages": [], "cursor": 0}').mode == "manual"
        state = SessionState(mode="auto")
        assert session_from_json(session_to_json(state)).mode == "auto"

    def test_auto_unbrowsed_is_empty(self):
        output, _ = build_browser(FakeHttp()).next_output('{"mode": "auto", "pages": [], "cursor": 0}')
        assert output.kind is OutputKind.EMPTY

    def test_set_mode_rejects_unknown(self):
        with pytest.raises(StateError):
            build_browser(FakeHttp()).restore(self.build_auto_state(FakeHttp())).set_mode("garbage")

    def test_mode_survives_search_and_paging(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            dict(make_post(5).raw), dict(make_post(6).raw),
        ]
        browser = build_browser(http)
        session = browser.restore(self.build_auto_state(http, selection=2))
        session.search(SearchConditions(site="danbooru"))  # 筛选变更 = 会话重置
        assert session.state.mode == "auto"
        session.goto_page(2)  # 翻页
        assert session.state.mode == "auto"

    def test_negative_cursor_clamped(self):
        http = FakeHttp()
        browser = build_browser(http)
        state = self.build_auto_state(http, selection=None)
        tampered = session_from_json(state)
        tampered.cursor = -5
        out, _ = browser.next_output(session_to_json(tampered))
        assert out.kind is OutputKind.IMAGE and out.post.id == 1  # 钳制到 0,不取 posts[-1]

    def test_fetch_cap_prevents_runaway(self):
        http = FakeHttp()
        # 站点忽略页码:永远返回同一页内容
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            dict(make_post(1).raw), dict(make_post(2).raw),
        ]
        browser = build_browser(http)
        state = session_from_json(self.build_auto_state(http, selection=None))
        state.cursor = 1000  # 篡改:远超已加载
        out, _ = browser.next_output(session_to_json(state))
        assert out.kind is OutputKind.EMPTY  # 拉取上限后停止,不无限循环


class TestSessionRestore:
    """T7 会话完整恢复:重开工作流回到保存时的浏览现场(issue #10)。"""

    def test_full_roundtrip_all_fields(self):
        # 全字段往返:条件(含排除/评级/排序/每页)、多页含 raw、游标、选中、列表、
        # 页码、模式、输出过滤
        state = SessionState(
            conditions=SearchConditions(
                site="danbooru", tags=("1girl",), exclude_tags=("nude",),
                ratings=frozenset({"g", "e"}), sort="score", per_page=60,
            ),
            pages=[Page(number=1, posts=[make_post(1, tags=("1girl", "nude"))]),
                   Page(number=2, posts=[make_post(2)])],
            cursor=3,
            selection=2,
            outlist=[1, 2],
            page=2,
            mode="list",
            out_filter=("nude",),
        )
        restored = session_from_json(session_to_json(state))
        assert restored == state  # 往返一致

    def test_reopen_same_conditions_preserves_cursor(self):
        # 自动模式保存时游标在中途,重开重拉(条件不变)不丢位置
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            dict(make_post(i).raw) for i in (1, 2, 3)
        ]
        browser = build_browser(http)
        state = SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(number=1, posts=[make_post(i) for i in (1, 2, 3)])],
            cursor=2, selection=3, mode="auto",
        )
        session = browser.restore(session_to_json(state))
        session.search(SearchConditions(site="danbooru"))  # 重开重拉:条件不变
        assert session.state.cursor == 2  # 自动位置保留(ADR-0002)
        assert session.state.selection == 3

    def test_reopen_auto_without_selection_preserves_cursor(self):
        # 自动模式无选中也推进:重开(条件不变)不丢位置
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            dict(make_post(i).raw) for i in (1, 2, 3)
        ]
        browser = build_browser(http)
        state = SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(number=1, posts=[make_post(i) for i in (1, 2, 3)])],
            cursor=2, selection=None, mode="auto",
        )
        session = browser.restore(session_to_json(state))
        session.search(SearchConditions(site="danbooru"))
        assert session.state.cursor == 2  # 不依赖选中

    def test_reopen_list_mode_preserves_cursor(self):
        # 列表模式永远无选中:重开后列表位置保留
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            dict(make_post(i).raw) for i in (1, 2)
        ]
        browser = build_browser(http)
        state = SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(number=1, posts=[make_post(i) for i in (1, 2)])],
            cursor=1, selection=None, mode="list", outlist=[1, 2],
        )
        session = browser.restore(session_to_json(state))
        session.search(SearchConditions(site="danbooru"))
        assert session.state.cursor == 1  # 列表位置保留
        assert session.state.mode == "list"

    def test_reopen_same_page_preserves_cursor(self):
        # 页码 >1 的重开走 goto_page(同页重拉),游标保留
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            dict(make_post(i).raw) for i in (1, 2)
        ]
        browser = build_browser(http)
        state = SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(number=2, posts=[make_post(i) for i in (1, 2)])],
            cursor=1, selection=2, page=2, mode="auto",
        )
        session = browser.restore(session_to_json(state))
        session.goto_page(2)  # 重开重拉同一页
        assert session.state.cursor == 1  # 游标保留
        assert session.state.page == 2

    def test_filter_change_still_resets_cursor(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [dict(make_post(5).raw)]
        browser = build_browser(http)
        state = SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(number=1, posts=[make_post(1)])], cursor=1, mode="auto",
        )
        session = browser.restore(session_to_json(state))
        session.search(SearchConditions(site="danbooru", tags=("blue_eyes",)))  # 筛选变更
        assert session.state.cursor == 0  # 变更即重置

    def test_credentials_never_in_session(self):
        # 凭据不进会话 JSON(T10 安全约束)
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [dict(make_post(1).raw)]
        session = build_browser(http).restore("")
        session.search(SearchConditions(site="danbooru"))
        serialized = session.serialize()
        assert "api_key" not in serialized
        assert "secret" not in serialized


class TestDownloadQuality:
    """下载质量:默认大图预览,原图开关下载原图(T8)。"""

    def build_state(self, http):
        posts = [make_post(1)]
        state = SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(number=1, posts=posts)], selection=1,
        )
        return session_to_json(state), posts[0]

    def test_default_downloads_sample(self):
        http = FakeHttp()
        state, post = self.build_state(http)
        http.bytes_responses[post.sample_url] = IMAGE_BYTES  # 只有 sample
        output, _ = build_browser(http).next_output(state)
        assert output.kind is OutputKind.IMAGE
        assert http.bytes_calls == [post.sample_url]  # 默认下载大图预览
        assert output.metadata["file_url"] == post.file_url  # 元数据仍是原图地址

    def test_original_switch_downloads_original(self):
        http = FakeHttp()
        state, post = self.build_state(http)
        http.bytes_responses[post.file_url] = IMAGE_BYTES  # 只有原图
        output, _ = build_browser(http).next_output(state, prefer_original=True)
        assert output.kind is OutputKind.IMAGE
        assert http.bytes_calls == [post.file_url]

    def test_sample_missing_falls_back_to_original(self):
        from dataclasses import replace
        http = FakeHttp()
        state, post = self.build_state(http)
        no_sample = replace(post, sample_url="")  # 站点没给 sample 时兜底原图
        state = session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(number=1, posts=[no_sample])], selection=1,
        ))
        http.bytes_responses[post.file_url] = IMAGE_BYTES
        output, _ = build_browser(http).next_output(state)
        assert output.kind is OutputKind.IMAGE  # sample 缺失 → 原图兜底
        assert http.bytes_calls == [post.file_url]

    def test_cache_keyed_by_download_url(self):
        # 同一帖子 sample 与原图是不同缓存项
        http = FakeHttp()
        state, post = self.build_state(http)
        http.bytes_responses[post.file_url] = IMAGE_BYTES
        http.bytes_responses[post.sample_url] = IMAGE_BYTES
        browser = build_browser(http, cache=MemoryCache())
        out1, _ = browser.next_output(state)
        assert out1.kind is OutputKind.IMAGE
        n = len(http.bytes_calls)
        out2, _ = browser.next_output(state, prefer_original=True)  # 原图 → 不同缓存项
        assert out2.kind is OutputKind.IMAGE
        assert len(http.bytes_calls) == n + 1  # 原图单独下载一次
        out3, _ = browser.next_output(state, prefer_original=True)
        assert len(http.bytes_calls) == n + 1  # 原图缓存命中

    def test_disk_cache_serves_repeat_execution(self, tmp_path):
        from core.disk_cache import DiskImageCache
        http = FakeHttp()
        state, post = self.build_state(http)
        http.bytes_responses[post.sample_url] = IMAGE_BYTES
        browser = build_browser(http, cache=DiskImageCache(str(tmp_path)))
        out1, _ = browser.next_output(state)
        assert out1.kind is OutputKind.IMAGE
        n = len(http.bytes_calls)
        out2, _ = browser.next_output(state)
        assert out2.kind is OutputKind.IMAGE
        assert len(http.bytes_calls) == n  # 磁盘缓存命中,不重复下载


class TestFailureStrategy:
    """T9:自动/列表跳过失败帖并标红,手动报错,空状态明确(issue #11)。"""

    def test_auto_skips_failed_and_marks(self):
        http = FakeHttp()
        posts = [make_post(1), make_post(2)]
        http.bytes_responses[posts[1].file_url] = IMAGE_BYTES
        http.bytes_responses[posts[1].sample_url] = IMAGE_BYTES  # 帖子 1 无字节 → 失败
        browser = build_browser(http)
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"), pages=[Page(1, posts)],
        )))
        session.set_mode("auto")
        out, s = browser.next_output(session.serialize())
        assert out.kind is OutputKind.IMAGE and out.post.id == 2  # 跳过 1,继续
        new_state = session_from_json(s)
        assert 1 in new_state.failed  # 失败帖记录(面板标红)
        assert new_state.cursor == 2  # 游标越过失败帖

    def test_auto_skips_animated(self):
        http = FakeHttp()
        posts = [make_post(1, file_ext="webm", animated=True), make_post(2)]
        http.bytes_responses[posts[1].file_url] = IMAGE_BYTES
        http.bytes_responses[posts[1].sample_url] = IMAGE_BYTES
        browser = build_browser(http)
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"), pages=[Page(1, posts)],
        )))
        session.set_mode("auto")
        out, s = browser.next_output(session.serialize())
        assert out.kind is OutputKind.IMAGE and out.post.id == 2  # 动画帖按失败跳过
        assert 1 in session_from_json(s).failed

    def test_auto_all_failed_reaches_end(self):
        http = FakeHttp()  # 全无字节 → 全部失败
        http.json_responses["https://danbooru.donmai.us/posts.json"] = []  # 下一页为空
        posts = [make_post(i) for i in (1, 2, 3)]
        browser = build_browser(http)
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"), pages=[Page(1, posts)],
        )))
        session.set_mode("auto")
        out, _ = browser.next_output(session.serialize())
        assert out.kind is OutputKind.EMPTY  # 跳过到最后 → 已到结果末尾

    def test_list_skips_failed_and_marks(self):
        http = FakeHttp()
        posts = [make_post(1), make_post(2)]
        http.bytes_responses[posts[1].file_url] = IMAGE_BYTES
        http.bytes_responses[posts[1].sample_url] = IMAGE_BYTES
        browser = build_browser(http)
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"), pages=[Page(1, posts)], outlist=[1, 2],
        )))
        session.set_mode("list")
        out, s = browser.next_output(session.serialize())
        assert out.kind is OutputKind.IMAGE and out.post.id == 2  # 跳过列表中的 1
        new_state = session_from_json(s)
        assert 1 in new_state.failed
        assert new_state.cursor == 2

    def test_list_all_dead_reports_after_cycle(self):
        http = FakeHttp()  # 全无字节 → 列表全失败
        posts = [make_post(1), make_post(2)]
        browser = build_browser(http)
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"), pages=[Page(1, posts)], outlist=[1, 2],
        )))
        session.set_mode("list")
        out, _ = browser.next_output(session.serialize())
        assert out.kind is OutputKind.EMPTY  # 一圈全失败 → 明确报错
        assert "下载失败" in (out.reason or "")  # 失败原因明细

    def test_list_refetches_missing_post_by_id(self):
        # 重开/换筛选后旧帖不在已加载结果:按 id 回源,列表照常输出
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts/5.json"] = dict(make_post(5).raw)
        http.bytes_responses[make_post(5).sample_url] = IMAGE_BYTES
        browser = build_browser(http)
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(1, [make_post(1)])],  # 5 不在已加载结果
            outlist=[5, 1],
        )))
        session.set_mode("list")
        out, s = browser.next_output(session.serialize())
        assert out.kind is OutputKind.IMAGE and out.post.id == 5  # 回源后正常输出

    def test_list_cache_serves_without_network(self):
        # 加入列表时快照帖子数据;换页丢页后列表输出用快照,零网络
        http = FakeHttp()
        post = make_post(5, tags=("1girl", "solo"))
        http.bytes_responses[post.sample_url] = IMAGE_BYTES
        browser = build_browser(http)
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(1, [post])],
        )))
        session.add_to_list(5)
        assert session.state.list_cache["5"]["tags"] == ["1girl", "solo"]  # 加入时快照
        session.set_mode("list")
        # 模拟翻页后帖子从页中被丢弃:pages 清空,list_cache 保留
        session.state.pages = []
        out, s = browser.next_output(session.serialize())
        assert out.kind is OutputKind.IMAGE and out.post.id == 5  # 快照直接输出
        assert http.json_calls == []  # 零网络回源

    def test_list_cache_pruned_on_remove_and_clear(self):
        http = FakeHttp()
        browser = build_browser(http)
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(1, [make_post(1), make_post(2)])],
        )))
        session.add_to_list(1)
        session.add_to_list(2)
        session.remove_from_list(1)
        assert "1" not in session.state.list_cache
        assert "2" in session.state.list_cache
        session.clear_list()
        assert session.state.list_cache == {}

    def test_cross_site_list_uses_posts_own_site(self):
        # 切换站点后列表帖仍按帖子自己的站点拉取(danbooru 帖在 gelbooru 会话下)
        http = FakeHttp()
        dan_post = make_post(7, tags=("1girl", "solo"))
        http.bytes_responses[dan_post.sample_url] = IMAGE_BYTES
        from sites.gelbooru import GelbooruSite
        browser = Browser(
            sites={"danbooru": DanbooruSite(http), "gelbooru": GelbooruSite(http, credentials={})},
        )
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="gelbooru"),  # 当前站是 gelbooru
            pages=[Page(1, [dan_post])],  # 快照里的帖子是 danbooru
            outlist=[7],
        )))
        session.add_to_list(7)
        session.set_mode("list")
        session.state.pages = []  # 模拟换站后旧页卸载
        out, _ = browser.next_output(session.serialize())
        assert out.kind is OutputKind.IMAGE and out.post.id == 7  # 按帖子自身站点输出
        assert out.prompt == "1girl, solo"  # danbooru 标签拼接

    def test_empty_results_manual_message(self):
        http = FakeHttp()
        state = SessionState(conditions=SearchConditions(site="danbooru"),
                             pages=[Page(number=1, posts=[])])
        out, _ = build_browser(http).next_output(session_to_json(state))
        assert out.kind is OutputKind.EMPTY
        assert "结果为空" in (out.reason or "")

    def test_failed_serializes_and_resets_on_search(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [dict(make_post(9).raw)]
        browser = build_browser(http)
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"), pages=[Page(1, [make_post(1)])],
            failed=[1],
        )))
        assert session_from_json(session.serialize()).failed == [1]  # 序列化往返
        session.search(SearchConditions(site="danbooru"))
        assert session.state.failed == []  # 新搜索重置失败标记


class TestPageCap:
    """会话页数上限:自动/翻页不无限膨胀,游标/标记一致维护。"""

    def test_cap_keeps_5_newest_pages(self):
        state = SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(number=n, posts=[make_post(n)]) for n in range(1, 9)],
            cursor=7, selection=8,
        )
        build_browser(FakeHttp())._cap_pages(state)
        assert [pg.number for pg in state.pages] == [4, 5, 6, 7, 8]  # 保留最新 5 页
        assert state.cursor == 4  # 丢弃 3 页(1-3)→ 游标平移 7-3
        assert state.selection == 8  # 选中在保留页中,不清

    def test_cap_clears_markers_in_dropped_pages(self):
        state = SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(number=n, posts=[make_post(n)]) for n in range(1, 7)],
            cursor=5, selection=1, last_output=1, failed=[1, 6],
        )
        build_browser(FakeHttp())._cap_pages(state)
        assert [pg.number for pg in state.pages] == [2, 3, 4, 5, 6]
        assert state.selection is None  # 选中 1 在被丢弃页(第 1 页)→ 清理
        assert state.last_output is None  # 红标 1 被清理
        assert state.failed == [6]  # 失败标记 1 清理,6 保留

    def test_goto_page_applies_cap(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [dict(make_post(9).raw)]
        browser = build_browser(http)
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(number=n, posts=[make_post(n)]) for n in range(1, 6)],
        )))
        session.goto_page(6)
        assert [pg.number for pg in session.state.pages] == [2, 3, 4, 5, 6]


class TestCurrentOutputMark:
    """T9 续:#19 红色=自动/列表当前输出,失败改 ✕ 徽标。"""

    def test_auto_output_records_last_output(self):
        http = FakeHttp()
        posts = [make_post(1), make_post(2)]
        for p in posts:
            http.bytes_responses[p.file_url] = IMAGE_BYTES
            http.bytes_responses[p.sample_url] = IMAGE_BYTES
        browser = build_browser(http)
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"), pages=[Page(1, posts)],
        )))
        session.set_mode("auto")
        out, s = browser.next_output(session.serialize())
        assert out.kind is OutputKind.IMAGE
        assert session_from_json(s).last_output == 1  # 当前输出帖记录

    def test_list_output_records_last_output(self):
        http = FakeHttp()
        posts = [make_post(1), make_post(2)]
        for p in posts:
            http.bytes_responses[p.file_url] = IMAGE_BYTES
            http.bytes_responses[p.sample_url] = IMAGE_BYTES
        browser = build_browser(http)
        session = browser.restore(session_to_json(SessionState(
            conditions=SearchConditions(site="danbooru"), pages=[Page(1, posts)], outlist=[2, 1],
        )))
        session.set_mode("list")
        out, s = browser.next_output(session.serialize())
        assert out.kind is OutputKind.IMAGE and out.post.id == 2
        assert session_from_json(s).last_output == 2

    def test_manual_output_does_not_record(self):
        http = FakeHttp()
        posts = [make_post(1), make_post(2, tags=("2girls", "hug"))]
        for p in posts:
            http.bytes_responses[p.file_url] = IMAGE_BYTES
            http.bytes_responses[p.sample_url] = IMAGE_BYTES
        browser = build_browser(http)
        out, s = browser.next_output(state_with_selection(http, selection=2))
        assert out.kind is OutputKind.IMAGE
        assert session_from_json(s).last_output is None  # 手动模式无红标

    def test_last_output_serializes_and_resets_on_search(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [dict(make_post(9).raw)]
        browser = build_browser(http)
        state = SessionState(conditions=SearchConditions(site="danbooru"),
                             pages=[Page(1, [make_post(1)])], last_output=1)
        assert session_from_json(session_to_json(state)).last_output == 1  # 往返
        session = browser.restore(session_to_json(state))
        session.search(SearchConditions(site="danbooru"))
        assert session.state.last_output is None  # 新搜索清理红标


class TestOutputFilter:
    """输出过滤:只剔除 Prompt 字符串中的标签,元数据忠实(issue #13)。"""

    def test_filtered_prompt_keeps_order(self):
        post = make_post(1, tags=("1girl", "nude", "long_hair", "blue_eyes"))
        browser = build_browser(FakeHttp())
        assert browser.derive_prompt(post, ("nude",)) == "1girl, long_hair, blue_eyes"
        assert browser.derive_prompt(post, ("nude", "1girl")) == "long_hair, blue_eyes"

    def test_all_filtered_yields_empty(self):
        post = make_post(1, tags=("nude", "1girl"))
        assert build_browser(FakeHttp()).derive_prompt(post, ("nude", "1girl")) == ""

    def test_output_prompt_filtered_metadata_faithful(self):
        http = FakeHttp()
        posts = [make_post(1), make_post(2, tags=("2girls", "hug", "nude"))]
        state = SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(1, posts)], selection=2, out_filter=("nude",),
        )
        http.bytes_responses[posts[1].file_url] = IMAGE_BYTES
        http.bytes_responses[posts[1].sample_url] = IMAGE_BYTES
        output, _ = build_browser(http).next_output(session_to_json(state))
        assert output.prompt == "2girls, hug"  # Prompt 已过滤
        assert output.metadata["tags"] == ["2girls", "hug", "nude"]  # 元数据忠实

    def test_set_out_filter_does_not_reset_session(self):
        http = FakeHttp()
        browser = build_browser(http)
        session = browser.restore(state_with_selection(http, selection=2))
        session.set_out_filter(("nude",))
        assert session.state.selection == 2  # 过滤不属于搜索条件,不触发重置
        assert session.state.out_filter == ("nude",)

    def test_out_filter_serializes(self):
        state = SessionState(out_filter=("nude", "1girl"))
        assert session_from_json(session_to_json(state)).out_filter == ("nude", "1girl")
        assert session_from_json('{"conditions": null, "pages": [], "cursor": 0}').out_filter == ()

    def test_out_filter_survives_search_and_paging(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [dict(make_post(5).raw)]
        browser = build_browser(http)
        session = browser.restore(state_with_selection(http, selection=2))
        session.set_out_filter(("nude",))
        session.search(SearchConditions(site="danbooru"))
        assert session.state.out_filter == ("nude",)  # 搜索重构不丢过滤
        session.goto_page(2)
        assert session.state.out_filter == ("nude",)  # 翻页重构不丢过滤


class TestListMode:
    """列表模式:策展列表操作 + 无限循环(issue #9)。"""

    def build_list_state(self, http, post_ids=(1, 2, 3), outlist=None):
        posts = [make_post(i) for i in post_ids]
        for p in posts:
            http.bytes_responses[p.file_url] = IMAGE_BYTES
            http.bytes_responses[p.sample_url] = IMAGE_BYTES
        state = SessionState(
            conditions=SearchConditions(site="danbooru"),
            pages=[Page(number=1, posts=posts)],
            outlist=list(outlist or []),
        )
        session = build_browser(http).restore(session_to_json(state))
        session.set_mode("list")
        return session

    def test_add_and_remove_from_list(self):
        http = FakeHttp()
        session = self.build_list_state(http)
        session.add_to_list(2)
        session.add_to_list(1)
        assert session.state.outlist == [2, 1]
        session.add_to_list(2)  # 去重:已存在则不重复加入
        assert session.state.outlist == [2, 1]
        session.remove_from_list(2)
        assert session.state.outlist == [1]
        with pytest.raises(StateError):
            session.add_to_list(999)  # 未加载帖子校验

    def test_insert_at_position(self):
        http = FakeHttp()
        session = self.build_list_state(http, post_ids=(1, 2, 3, 4), outlist=[1, 3])
        session.insert_to_list(2, index=1)
        assert session.state.outlist == [1, 2, 3]
        session.insert_to_list(4, index=99)  # 越界钳制到末尾
        assert session.state.outlist == [1, 2, 3, 4]

    def test_clear_list(self):
        http = FakeHttp()
        session = self.build_list_state(http, outlist=[1, 2])
        session.clear_list()
        assert session.state.outlist == []

    def test_list_mode_cycles_infinitely(self):
        http = FakeHttp()
        session = self.build_list_state(http, outlist=[2, 1])
        browser = build_browser(http)
        out1, s1 = browser.next_output(session.serialize())
        assert out1.kind is OutputKind.IMAGE and out1.post.id == 2  # 列表顺序输出
        assert browser.restore(s1).state.cursor == 1
        out2, s2 = browser.next_output(s1)
        assert out2.post.id == 1
        out3, s3 = browser.next_output(s2)  # 末尾回绕 → 无限循环
        assert out3.post.id == 2
        assert browser.restore(s3).state.cursor == 1

    def test_list_mode_empty_list(self):
        http = FakeHttp()
        session = self.build_list_state(http, outlist=[])
        out, _ = build_browser(http).next_output(session.serialize())
        assert out.kind is OutputKind.EMPTY
        assert "列表为空" in (out.reason or "")

    def test_list_post_not_loaded_skipped_and_marked(self):
        # T9:不在已加载结果的帖子按失败跳过并标红,继续列表下一张
        http = FakeHttp()
        session = self.build_list_state(http, outlist=[999, 1])
        browser = build_browser(http)
        out, s = browser.next_output(session.serialize())
        assert out.kind is OutputKind.IMAGE and out.post.id == 1  # 跳过 999,输出 1
        new_state = browser.restore(s).state
        assert 999 in new_state.failed  # 标红
        assert new_state.cursor == 2  # 游标越过失败项

    def test_list_mode_select_does_not_move_cursor(self):
        http = FakeHttp()
        session = self.build_list_state(http, outlist=[2, 1])
        session.select(2)  # 列表模式下选中不扰动列表游标
        assert session.state.cursor == 0

    def test_reset_cursor_in_list_mode_goes_to_list_start(self):
        http = FakeHttp()
        session = self.build_list_state(http, outlist=[2, 1])
        session.state.cursor = 1
        session.reset_cursor()
        assert session.state.cursor == 0

    def test_set_mode_list_resets_cursor(self):
        http = FakeHttp()
        session = self.build_list_state(http, outlist=[2, 1])
        session.state.cursor = 7  # 模拟乱游标
        session.set_mode("list")
        assert session.state.cursor == 0

    def test_outlist_serializes_and_survives_search_reset(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [dict(make_post(9).raw)]
        browser = build_browser(http)
        session = self.build_list_state(http, outlist=[1, 2])
        session.search(SearchConditions(site="danbooru"))  # 筛选变更重置
        assert session.state.outlist == [1, 2]  # 显式策展不因筛选变化而丢
        assert session_from_json(session.serialize()).outlist == [1, 2]


class TestPagination:
    def test_goto_page_fetches_page_and_accumulates(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            dict(make_post(5).raw), dict(make_post(6).raw),
        ]
        browser = build_browser(http)
        session = browser.restore(state_with_selection(http, selection=2))
        result = session.goto_page(2)
        assert [p.id for p in result.posts] == [5, 6]
        state = browser.restore(session.serialize()).state
        assert state.page == 2  # 当前页序列化
        assert {pg.number for pg in state.pages} == {1, 2}  # 多页累积
        assert state.selection is None  # 原选中 2 不在新页中 → 清空

    def test_goto_page_keeps_selection_when_in_new_page(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [dict(make_post(2).raw)]
        browser = build_browser(http)
        session = browser.restore(state_with_selection(http, selection=2))
        session.goto_page(2)
        assert session.state.selection == 2  # 新页含原选中 → 保留(ADR-0002)

    def test_goto_page_replaces_same_page(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [dict(make_post(9).raw)]
        browser = build_browser(http)
        session = browser.restore(state_with_selection(http))
        session.goto_page(1)
        assert {pg.number for pg in session.state.pages} == {1}  # 覆盖而非重复

    def test_goto_page_requires_browsed_session(self):
        with pytest.raises(StateError):
            build_browser(FakeHttp()).restore("").goto_page(2)

    def test_page_defaults_to_one_and_roundtrips(self):
        assert session_from_json('{"conditions": null, "pages": [], "cursor": 0}').page == 1
        state = SessionState(page=3)
        assert session_from_json(session_to_json(state)).page == 3

    def test_goto_page_rejects_invalid_page(self):
        browser = build_browser(FakeHttp())
        for bad in (0, -3):
            with pytest.raises(StateError):
                browser.restore(state_with_selection(FakeHttp())).goto_page(bad)

    def test_goto_page_empty_results_not_accumulated(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = []  # 越界空页
        browser = build_browser(http)
        session = browser.restore(state_with_selection(http, selection=2))
        session.goto_page(50)
        assert session.state.page == 50  # 页码仍记录,重开工作流会重拉
        assert {pg.number for pg in session.state.pages} == {1}  # 空页不入列
