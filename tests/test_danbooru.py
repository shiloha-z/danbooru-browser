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
        assert params["tags"] == "1girl"
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

    def test_rating_and_sort_mapped_into_tags(self):
        http = FakeHttp()
        http.json_responses["https://danbooru.donmai.us/posts.json"] = []
        site = DanbooruSite(http)
        site.search(
            SearchConditions(site="danbooru", tags=("1girl",), ratings=frozenset({"g", "e"}),
                             sort="score", per_page=20),
            1,
        )
        tags_param = http.json_calls[-1][1]["tags"]
        for token in ("1girl", "rating:g", "rating:e", "order:score"):
            assert token in tags_param

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

    def test_fetch_image(self):
        http = FakeHttp()
        http.bytes_responses["https://cdn.example/1.jpg"] = b"\xff\xd8"
        site = DanbooruSite(http)
        assert site.fetch_image(make_post(1)) == b"\xff\xd8"
        assert http.bytes_calls == ["https://cdn.example/1.jpg"]

    def test_fetch_image_transport_error_propagates(self):
        site = DanbooruSite(FakeHttp())
        with pytest.raises(TransportError):
            site.fetch_image(make_post(1))
