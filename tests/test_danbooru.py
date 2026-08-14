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
    """首次请求指定 URL 抛 TransportError(模拟 danbooru 500),后续请求正常。"""

    def __init__(self, fail_once_urls=()) -> None:
        super().__init__()
        self._fail_urls = set(fail_once_urls)

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        self.json_calls.append((url, params))
        if url in self._fail_urls:
            self._fail_urls.remove(url)
            raise TransportError(f"HTTP 500: {url}", status=500)
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
        url, params = http.json_calls[-1]
        assert url == "https://danbooru.donmai.us/posts.json"
        assert params["page"] == 3
        assert params["limit"] == 40
        assert params["tags"] == "1girl rating:g order:id_desc"  # 默认评级普通 + 最新映射
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
        site.search(SearchConditions(site="danbooru", tags=("1girl",),
                                     ratings=frozenset({"g", "s", "q", "e"}), per_page=20), 1)
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
        seed = random_tags.split("order:random:")[1]
        assert seed.isdigit()
        site.search(SearchConditions(site="danbooru", sort="new", per_page=20), 1)
        # 最新显式映射 order:id_desc(danbooru 的 order:id 是升序旧帖优先)
        assert http.json_calls[-1][1]["tags"] == "rating:g order:id_desc"

    def test_exclude_tags_mapped_with_dash(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = []
        site = DanbooruSite(http)
        site.search(SearchConditions(site="danbooru", tags=("1girl",),
                                     exclude_tags=("nude", "blood"), per_page=20), 1)
        tags_param = http.json_calls[-1][1]["tags"]
        assert "-nude" in tags_param and "-blood" in tags_param

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
        assert http.json_calls[0][1]["tags"] == "1girl rating:g order:score"
        assert http.json_calls[1][1]["tags"] == "1girl rating:g order:rank"

    def test_non_score_500_does_not_fall_back(self):
        http = FlakyHttp(fail_once_urls=["https://danbooru.donmai.us/posts.json"])
        http.json_responses["https://danbooru.donmai.us/posts.json"] = [raw_post(1)]
        site = DanbooruSite(http)
        with pytest.raises(TransportError):
            site.search(SearchConditions(site="danbooru", tags=("1girl",), sort="new", per_page=20), 1)
        assert len(http.json_calls) == 1  # 非 score 排序不重试

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
        url, params = http.json_calls[-1]
        assert params["search[query]"] == "1girl"
        assert params["search[type]"] == "tag_query"

    def test_fetch_image_transport_error_propagates(self):
        site = DanbooruSite(FakeHttp())
        with pytest.raises(TransportError):
            site.fetch_image(make_post(1))
