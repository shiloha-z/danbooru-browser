"""Danbooru site adapter: response parsing and search parameter mapping."""

from __future__ import annotations

import pytest

from core.errors import TransportError
from core.model import SearchConditions
from sites.danbooru import DanbooruSite, parse_post

from fakes import FakeHttp, make_post


def raw_post(post_id: int = 42, **overrides) -> dict:
    p = make_post(post_id)
    raw = dict(p.raw)
    if "tags" in overrides:  # raw 响应里的键是 tag_string
        overrides["tag_string"] = overrides.pop("tags")
    raw.update(overrides)
    return raw


class FlakyHttp(FakeHttp):
    """首次请求指定 URL 抛 TransportError(模拟 danbooru 4xx/5xx),后续请求正常。"""

    def __init__(self, fail_once_urls=(), status: int = 500) -> None:
        super().__init__()
        self._fail_urls = set(fail_once_urls)
        self._status = status

    def get_json(self, url: str, params: dict[str, Any] | None = None,
                 auth: tuple[str, str] | None = None) -> Any:
        self.json_calls.append((url, params, auth))
        if url in self._fail_urls:
            self._fail_urls.remove(url)
            raise TransportError(f"HTTP {self._status}: {url}", status=self._status)
        try:
            return self.json_responses[url]
        except KeyError:
            raise TransportError(f"no canned response for {url}") from None


class TestParsePost:
    def test_maps_fields(self):
        p = parse_post(
            raw_post(tags="1girl long_hair blue_eyes", rating="s", score=88,
                     tag_string_artist="foo bar", file_ext="jpg"),
            site="danbooru",
        )
        assert p.id == 42
        assert p.site == "danbooru"
        assert p.tags == ("1girl", "long_hair", "blue_eyes")
        assert p.rating == "s"
        assert p.score == 88
        assert p.author == "foo bar"
        assert not p.animated
        assert p.raw["id"] == 42  # raw response preserved for metadata

    def test_marks_animated_extensions(self):
        for ext in ("webm", "gif", "swf"):
            assert parse_post(raw_post(file_ext=ext), "danbooru").animated
        assert not parse_post(raw_post(file_ext="png"), "danbooru").animated

    def test_file_url_fallback_to_large(self):
        p = parse_post(raw_post(file_url=None, large_file_url="https://cdn.example/42_l.jpg"), "danbooru")
        assert p.file_url == "https://cdn.example/42_l.jpg"

    def test_empty_tag_string(self):
        p = parse_post(raw_post(tags="", tag_string_artist=""), "danbooru")
        assert p.tags == ()
        assert p.author == ""


class TestSearch:
    def test_params_and_parsing(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            raw_post(1), raw_post(2),
        ]
        site = DanbooruSite(http)
        result = site.search(
            SearchConditions(site="danbooru", tags=("1girl",), per_page=40),
            page=3,
        )
        url, params, _ = http.json_calls[-1]
        assert url == "https://danbooru.donmai.us/posts.json"
        assert params["page"] == 3
        assert params["limit"] == 40
        assert params["tags"] == "1girl order:id_desc"  # 默认 sort=new → 显式最新映射
        assert [p.id for p in result.posts] == [1, 2]
        assert result.page == 3
        assert not result.has_next  # 2 < limit 40

    def test_has_next_when_full_page(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            raw_post(i) for i in range(2)
        ]
        site = DanbooruSite(http)
        result = site.search(SearchConditions(site="danbooru", per_page=2), 1)
        assert result.has_next

    def test_partial_ratings_joined_with_or(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = []
        site = DanbooruSite(http)
        site.search(
            SearchConditions(site="danbooru", tags=("1girl",), ratings=frozenset({"g", "e"}),
                             sort="score", per_page=20),
            1,
        )
        tags_param = http.json_calls[-1][1]["tags"]
        # danbooru 空格分隔是 AND:多选评级必须用 ~(OR),否则选多个评级必然空结果
        assert "rating:g~rating:e" in tags_param
        assert "order:score" in tags_param

    def test_all_ratings_selected_emits_no_rating_filter(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = []
        site = DanbooruSite(http)
        site.search(SearchConditions(site="danbooru", tags=("1girl",), per_page=20), 1)
        tags_param = http.json_calls[-1][1]["tags"]
        assert "rating:" not in tags_param

    def test_single_rating_selected_is_plain_filter(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = []
        site = DanbooruSite(http)
        site.search(SearchConditions(site="danbooru", ratings=frozenset({"e"}), per_page=20), 1)
        tags_param = http.json_calls[-1][1]["tags"]
        assert tags_param == "rating:e order:id_desc"

    def test_sort_mapping(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = []
        site = DanbooruSite(http)
        site.search(SearchConditions(site="danbooru", sort="random", per_page=20), 1)
        # 随机必须带 seed:裸 order:random 在 danbooru API 上 500(2026-08 实测)
        random_tags = http.json_calls[-1][1]["tags"]
        assert random_tags.startswith("order:random:")
        assert random_tags[len("order:random:"):].isdigit()
        site.search(SearchConditions(site="danbooru", sort="new", per_page=20), 1)
        # 最新显式映射 order:id_desc(danbooru 的 order:id 是升序旧帖优先)
        assert http.json_calls[-1][1]["tags"] == "order:id_desc"

    def test_exclude_tags_mapped_with_dash(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = []
        site = DanbooruSite(http)
        site.search(SearchConditions(site="danbooru", tags=("1girl",),
                                     exclude_tags=("nude", "blood"), per_page=20), 1)
        tags_param = http.json_calls[-1][1]["tags"]
        assert "-nude" in tags_param and "-blood" in tags_param

    def test_hide_videos_maps_to_video_exclude(self):
        # danbooru 的 video 标签覆盖视频帖(实测),排除即可过滤
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = []
        site = DanbooruSite(http)
        site.search(SearchConditions(site="danbooru", tags=("1girl",),
                                     hide_videos=True, per_page=20), 1)
        assert "-video" in http.json_calls[-1][1]["tags"]

    def test_hide_videos_filters_animated_client_side(self):
        # -video 标签外,客户端按 animated 兜底(gif/缺标签的视频帖)
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            raw_post(1, file_ext="webm"), raw_post(2, file_ext="gif"), raw_post(3),
        ]
        site = DanbooruSite(http)
        result = site.search(SearchConditions(site="danbooru", hide_videos=True, per_page=20), 1)
        assert [p.id for p in result.posts] == [3]

    def test_transport_error_propagates(self):
        http = FakeHttp()  # no canned response
        site = DanbooruSite(http)
        with pytest.raises(TransportError):
            site.search(SearchConditions(site="danbooru"), 1)

    def test_score_sort_falls_back_to_rank_on_500(self):
        # danbooru 对含普通标签的 order:score 稳定 500(2026-08 实测),降级 order:rank
        http = FlakyHttp(fail_once_urls=["https://danbooru.donmai.us/posts.json"])
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [raw_post(1)]
        site = DanbooruSite(http)
        result = site.search(SearchConditions(site="danbooru", tags=("1girl",), sort="score", per_page=20), 1)
        assert [p.id for p in result.posts] == [1]
        assert http.json_calls[0][1]["tags"] == "1girl order:score"
        assert http.json_calls[1][1]["tags"] == "1girl order:rank"

    def test_non_score_500_does_not_fall_back(self):
        http = FlakyHttp(fail_once_urls=["https://danbooru.donmai.us/posts.json"])
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [raw_post(1)]
        site = DanbooruSite(http)
        with pytest.raises(TransportError):
            site.search(SearchConditions(site="danbooru", tags=("1girl",), sort="new", per_page=20), 1)
        assert len(http.json_calls) == 1  # 非 score 排序不重试

    def test_exclude_with_order_retries_without_order_on_422(self):
        # danbooru:正标签+负标签+order 元标签组合稳定 422(2026-08 实测);
        # 去掉 order 令牌重试,排序降级为默认
        http = FlakyHttp(fail_once_urls=["https://danbooru.donmai.us/posts.json"], status=422)
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [raw_post(1)]
        site = DanbooruSite(http)
        result = site.search(SearchConditions(site="danbooru", tags=("1girl",),
                                              exclude_tags=("nude",), per_page=20), 1)
        assert [p.id for p in result.posts] == [1]
        assert http.json_calls[0][1]["tags"] == "1girl order:id_desc -nude"
        assert http.json_calls[1][1]["tags"] == "1girl -nude"  # order 已去除

    def test_non_exclude_422_propagates(self):
        http = FlakyHttp(fail_once_urls=["https://danbooru.donmai.us/posts.json"], status=422)
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [raw_post(1)]
        site = DanbooruSite(http)
        with pytest.raises(TransportError):
            site.search(SearchConditions(site="danbooru", tags=("1girl",), per_page=20), 1)
        assert len(http.json_calls) == 1  # 无负标签不重试

    def test_multi_exclude_422_filters_remaining_client_side(self):
        # 多负标签(danbooru 恒 422,实测):重试只保留第一个负标签,其余客户端过滤
        http = FlakyHttp(fail_once_urls=["https://danbooru.donmai.us/posts.json"], status=422)
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [
            dict(make_post(1, tags=("1girl", "blood")).raw),  # 含第二个负标签 → 客户端过滤
            dict(make_post(2, tags=("1girl",)).raw),
        ]
        site = DanbooruSite(http)
        result = site.search(SearchConditions(site="danbooru", tags=("1girl",),
                                              exclude_tags=("nude", "blood"), per_page=20), 1)
        assert [p.id for p in result.posts] == [2]
        assert http.json_calls[1][1]["tags"] == "1girl -nude"  # 重试:去 order + 单负标签

    def test_hide_videos_422_retries_without_order(self):
        # hide_videos 产生的 -video 负标签同样触发 422 降级重试(之前只认 exclude_tags)
        http = FlakyHttp(fail_once_urls=["https://danbooru.donmai.us/posts.json"], status=422)
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [raw_post(1)]
        site = DanbooruSite(http)
        result = site.search(SearchConditions(site="danbooru", tags=("1girl",),
                                              hide_videos=True, per_page=20), 1)
        assert [p.id for p in result.posts] == [1]
        assert "-video" in http.json_calls[0][1]["tags"] and "order:" in http.json_calls[0][1]["tags"]
        assert "order:" not in http.json_calls[1][1]["tags"]  # 重试已去 order

    def test_basic_auth_when_configured(self, monkeypatch, tmp_path):
        from sites import credentials as cred_mod
        monkeypatch.setattr(cred_mod, "_CONFIG_PATH", str(tmp_path / "credentials.json"))
        cred_mod.save_credentials("danbooru", {"login": "zeloliu", "api_key": "secret"})
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = []
        DanbooruSite(http).search(SearchConditions(site="danbooru", per_page=20), 1)
        assert http.json_calls[-1][2] == ("zeloliu", "secret")

    def test_anonymous_without_credentials(self, monkeypatch, tmp_path):
        from sites import credentials as cred_mod
        monkeypatch.setattr(cred_mod, "_CONFIG_PATH", str(tmp_path / "empty.json"))
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = []
        DanbooruSite(http).search(SearchConditions(site="danbooru", per_page=20), 1)
        assert http.json_calls[-1][2] is None  # 未配置 → 匿名(行为不劣化)

    def test_fetch_image(self):
        http = FakeHttp()
        http.bytes_responses["https://cdn.example/1.jpg"] = b"\xff\xd8"
        site = DanbooruSite(http)
        assert site.fetch_image(make_post(1)) == b"\xff\xd8"
        assert http.bytes_calls == ["https://cdn.example/1.jpg"]

    def test_autocomplete_tags_maps_values(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/autocomplete.json"] = [
            {"value": "1girl"}, {"type": "category", "value": ""}, {"value": "1girl_solo"},
        ]
        site = DanbooruSite(http)
        assert site.autocomplete_tags("1girl") == ["1girl", "1girl_solo"]
        url, params, _ = http.json_calls[-1]
        assert params["search[query]"] == "1girl"
        assert params["search[type]"] == "tag_query"

    def test_fetch_image_transport_error_propagates(self):
        site = DanbooruSite(FakeHttp())
        with pytest.raises(TransportError):
            site.fetch_image(make_post(1))
