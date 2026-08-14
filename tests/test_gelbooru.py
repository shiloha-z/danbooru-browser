"""Gelbooru site adapter: response parsing and search parameter mapping."""

from __future__ import annotations

import pytest

from core.errors import StateError, TransportError
from core.model import SearchConditions
from sites.gelbooru import GelbooruSite, parse_post

from fakes import FakeHttp

CREDS = {"user_id": "123", "api_key": "testkey"}


def raw_post(post_id: int = 42, **overrides) -> dict:
    d = {
        "id": post_id,
        "tags": "1girl long_hair blue_eyes",
        "rating": "s",
        "score": 88,
        "creator": "foo bar",
        "image": "ab.jpg",
        "file_url": f"https://img3.gelbooru.com/images/ab/{post_id}.jpg",
        "preview_url": f"https://img3.gelbooru.com/thumbnails/ab/thumb_{post_id}.jpg",
        "sample_url": f"https://img3.gelbooru.com/samples/ab/sample_{post_id}.jpg",
    }
    d.update(overrides)
    return d


class TestParsePost:
    def test_maps_fields(self):
        p = parse_post(raw_post(tags="1girl long_hair blue_eyes", rating="s", score=88,
                                creator="foo bar"), site="gelbooru")
        assert p.id == 42
        assert p.site == "gelbooru"
        assert p.tags == ("1girl", "long_hair", "blue_eyes")
        assert p.rating == "s"
        assert p.score == 88
        assert p.author == "foo bar"
        assert p.preview_url.endswith("thumb_42.jpg")
        assert not p.animated
        assert p.raw["id"] == 42

    def test_marks_animated_extensions(self):
        for ext in ("webm", "gif"):
            assert parse_post(raw_post(image=f"a.{ext}"), "gelbooru").animated
        assert not parse_post(raw_post(image="a.png"), "gelbooru").animated

    def test_file_url_fallback_to_sample(self):
        p = parse_post(raw_post(file_url=None), "gelbooru")
        assert p.file_url.endswith("sample_42.jpg")


class TestSearch:
    def test_params_and_parsing(self):
        http = FakeHttp()
        http.json_responses["https://gelbooru.com/index.php"] = {"post": [raw_post(1), raw_post(2)]}
        site = GelbooruSite(http, credentials=CREDS)
        result = site.search(
            SearchConditions(site="gelbooru", tags=("1girl",), per_page=40), page=3,
        )
        url, params, _ = http.json_calls[-1]
        assert url == "https://gelbooru.com/index.php"
        assert params["pid"] == 2  # 页码 0 起:page-1
        assert params["limit"] == 40
        assert params["json"] == "1"
        assert params["tags"] == "1girl sort:id"  # 默认 sort=new → 上传 id 降序(最新)
        assert params["api_key"] == "testkey"
        assert params["user_id"] == "123"
        assert [p.id for p in result.posts] == [1, 2]
        assert result.page == 3

    def test_single_rating_filter(self):
        http = FakeHttp()
        http.json_responses["https://gelbooru.com/index.php"] = {"post": []}
        site = GelbooruSite(http, credentials=CREDS)
        site.search(SearchConditions(site="gelbooru", ratings=frozenset({"e"}), per_page=20), 1)
        assert "rating:e" in http.json_calls[-1][1]["tags"]

    def test_multi_rating_rejected(self):
        # gelbooru 无 OR 运算,评级只能单选(实测 ~ 语法全部无效)
        http = FakeHttp()
        site = GelbooruSite(http, credentials=CREDS)
        with pytest.raises(StateError):
            site.search(SearchConditions(site="gelbooru", ratings=frozenset({"g", "e"}), per_page=20), 1)

    def test_capabilities_single_rating(self):
        assert GelbooruSite(FakeHttp(), credentials=CREDS).capabilities.multi_rating is False

    def test_sort_mapping(self):
        http = FakeHttp()
        http.json_responses["https://gelbooru.com/index.php"] = {"post": []}
        site = GelbooruSite(http, credentials=CREDS)
        site.search(SearchConditions(site="gelbooru", sort="score", per_page=20), 1)
        assert "sort:score" in http.json_calls[-1][1]["tags"]
        site.search(SearchConditions(site="gelbooru", sort="random", per_page=20), 1)
        assert "sort:random" in http.json_calls[-1][1]["tags"]

    def test_exclude_mapped_with_dash(self):
        http = FakeHttp()
        http.json_responses["https://gelbooru.com/index.php"] = {"post": []}
        site = GelbooruSite(http, credentials=CREDS)
        site.search(SearchConditions(site="gelbooru", tags=("1girl",),
                                     exclude_tags=("nude",), per_page=20), 1)
        assert "-nude" in http.json_calls[-1][1]["tags"]

    def test_hide_videos_maps_to_video_exclude(self):
        http = FakeHttp()
        http.json_responses["https://gelbooru.com/index.php"] = {"post": []}
        site = GelbooruSite(http, credentials=CREDS)
        site.search(SearchConditions(site="gelbooru", hide_videos=True, per_page=20), 1)
        assert "-video" in http.json_calls[-1][1]["tags"]

    def test_missing_credentials_raise_clear_error(self):
        http = FakeHttp()
        site = GelbooruSite(http, credentials={})  # 未配置凭据
        with pytest.raises(StateError) as exc:
            site.search(SearchConditions(site="gelbooru", per_page=20), 1)
        assert "credentials.json" in str(exc.value)

    def test_empty_response(self):
        http = FakeHttp()
        http.json_responses["https://gelbooru.com/index.php"] = {}
        site = GelbooruSite(http, credentials=CREDS)
        result = site.search(SearchConditions(site="gelbooru", per_page=20), 1)
        assert result.posts == ()

    def test_credentials_read_fresh_at_request_time(self, monkeypatch, tmp_path):
        from sites import credentials as cred_mod
        monkeypatch.setattr(cred_mod, "_CONFIG_PATH", str(tmp_path / "credentials.json"))
        cred_mod.save_credentials("gelbooru", {"user_id": "1", "api_key": "k1"})
        http = FakeHttp()
        http.json_responses["https://gelbooru.com/index.php"] = {"post": []}
        site = GelbooruSite(http)  # 不注入 → 每次请求实时读文件
        site.search(SearchConditions(site="gelbooru", per_page=20), 1)
        assert http.json_calls[-1][1]["api_key"] == "k1"
        cred_mod.save_credentials("gelbooru", {"api_key": "k2"})  # 面板保存更新
        site.search(SearchConditions(site="gelbooru", per_page=20), 1)
        assert http.json_calls[-1][1]["api_key"] == "k2"  # 立即生效,无需重启

    def test_fetch_image(self):
        http = FakeHttp()
        http.bytes_responses["https://img3.gelbooru.com/images/ab/42.jpg"] = b"\xff\xd8"
        site = GelbooruSite(http, credentials=CREDS)
        post = parse_post(raw_post(), "gelbooru")
        assert site.fetch_image(post) == b"\xff\xd8"
