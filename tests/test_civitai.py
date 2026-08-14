"""Civitai site adapter: image parsing, model search, nsfw mapping (issue #7)."""

from __future__ import annotations

import pytest

from core.errors import StateError
from core.model import SearchConditions
from sites.civitai import CivitaiSite, parse_post

from fakes import FakeHttp


def raw_image(image_id: int = 42, **overrides) -> dict:
    d = {
        "id": image_id,
        "url": f"https://image.civitai.com/tk/{image_id}/original=true/{image_id}.jpeg",
        "nsfw": False,
        "width": 1024,
        "height": 1024,
        "meta": {"prompt": "1girl, masterpiece"},
        "model": {"name": "Test Model"},
        "modelVersion": {"id": 7, "name": "v1"},
        "tags": ["anime"],
    }
    d.update(overrides)
    return d


class TestParsePost:
    def test_maps_fields(self):
        p = parse_post(raw_image(), "civitai")
        assert p.id == 42
        assert p.site == "civitai"
        assert p.file_url.endswith("original=true/42.jpeg")
        assert p.sample_url.endswith("original=false/42.jpeg")  # 压缩版作预览/大图
        assert p.preview_url.endswith("original=false/42.jpeg")
        assert p.rating == "g"  # nsfw False
        assert not p.animated
        assert p.raw["model"]["name"] == "Test Model"

    def test_nsfw_true_maps_to_r18_rating(self):
        p = parse_post(raw_image(nsfw=True), "civitai")
        assert p.rating == "e"

    def test_mp4_video_marked_animated(self):
        # civitai 有 mp4 视频:必须按动画处理,否则下载视频字节被当图片转换崩溃
        p = parse_post(raw_image(url="https://image.civitai.com/tk/9/original=true/9.mp4"), "civitai")
        assert p.animated

    def test_prompt_reads_from_meta(self):
        p = parse_post(raw_image(), "civitai")
        assert p.raw["meta"]["prompt"] == "1girl, masterpiece"
        assert parse_post(raw_image(meta={}), "civitai").raw.get("meta") == {}


class TestSearch:
    def test_hide_videos_filters_animated(self):
        # civitai 无标签体系,拉取后过滤视频项
        http = FakeHttp()
        http.json_responses["https://civitai.com/api/v1/images"] = {
            "items": [
                raw_image(1),
                raw_image(2, url="https://image.civitai.com/tk/2/original=true/2.mp4"),
            ],
        }
        site = CivitaiSite(http)
        result = site.search(SearchConditions(site="civitai", model_id=1,
                                              hide_videos=True, per_page=20), 1)
        assert [p.id for p in result.posts] == [1]  # mp4 被过滤

    def test_search_by_model_id(self):
        http = FakeHttp()
        http.json_responses["https://civitai.com/api/v1/images"] = {"items": [raw_image(1)]}
        site = CivitaiSite(http)
        result = site.search(SearchConditions(site="civitai", model_id=16014, per_page=40), page=2)
        url, params, _ = http.json_calls[-1]
        assert url == "https://civitai.com/api/v1/images"
        assert params["modelId"] == 16014
        assert params["page"] == 2
        assert params["limit"] == 40
        assert [p.id for p in result.posts] == [1]

    def test_search_requires_model(self):
        site = CivitaiSite(FakeHttp())
        with pytest.raises(StateError):
            site.search(SearchConditions(site="civitai", per_page=20), 1)

    def test_nsfw_mapping(self):
        http = FakeHttp()
        http.json_responses["https://civitai.com/api/v1/images"] = {"items": []}
        site = CivitaiSite(http)
        site.search(SearchConditions(site="civitai", model_id=1, ratings=frozenset({"g"}),
                                     per_page=20), 1)
        assert http.json_calls[-1][1].get("nsfw") == "None"
        site.search(SearchConditions(site="civitai", model_id=1, ratings=frozenset({"s", "q"}),
                                     per_page=20), 1)
        assert http.json_calls[-1][1].get("nsfw") == "Soft"  # s/q 都映射 Soft
        site.search(SearchConditions(site="civitai", model_id=1, ratings=frozenset({"e"}),
                                     per_page=20), 1)
        assert http.json_calls[-1][1].get("nsfw") == "X"

    def test_multi_nsfw_rejected(self):
        # civitai nsfw 参数单选(实测多值 400)
        http = FakeHttp()
        site = CivitaiSite(http)
        with pytest.raises(StateError):
            site.search(SearchConditions(site="civitai", model_id=1,
                                         ratings=frozenset({"g", "e"}), per_page=20), 1)

    def test_sort_mapping(self):
        http = FakeHttp()
        http.json_responses["https://civitai.com/api/v1/images"] = {"items": []}
        site = CivitaiSite(http)
        site.search(SearchConditions(site="civitai", model_id=1, sort="new", per_page=20), 1)
        assert http.json_calls[-1][1]["sort"] == "Newest"
        site.search(SearchConditions(site="civitai", model_id=1, sort="score", per_page=20), 1)
        assert http.json_calls[-1][1]["sort"] == "Most Reactions"

    def test_unsupported_sort_raises(self):
        # random 不在 civitai 能力内:报错而非静默降级(审查发现静默映射 Newest)
        site = CivitaiSite(FakeHttp())
        with pytest.raises(StateError):
            site.search(SearchConditions(site="civitai", model_id=1, sort="random", per_page=20), 1)

    def test_search_models(self):
        http = FakeHttp()
        http.json_responses["https://civitai.com/api/v1/models"] = {
            "items": [{"id": 16014, "name": "Anime Style"}, {"id": 2, "name": "X Style"}],
        }
        site = CivitaiSite(http)
        models = site.search_models("anime")
        assert models == [{"id": 16014, "name": "Anime Style"}, {"id": 2, "name": "X Style"}]
        assert http.json_calls[-1][1]["query"] == "anime"

    def test_capabilities(self):
        caps = CivitaiSite(FakeHttp()).capabilities
        assert caps.has_tag_search is False
        assert caps.has_exclude_tags is False
        assert caps.has_model_search is True
        assert caps.multi_rating is False
        assert caps.prompt_kind == "embedded"
        assert "random" not in caps.sort_options

    def test_fetch_image(self):
        http = FakeHttp()
        http.bytes_responses["https://image.civitai.com/tk/1/original=false/1.jpeg"] = b"\xff\xd8"
        site = CivitaiSite(http)
        post = parse_post(raw_image(1), "civitai")
        assert site.fetch_image(post, post.sample_url) == b"\xff\xd8"
