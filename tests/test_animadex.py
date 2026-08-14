"""AnimaDex 浏览器:搜索/分面/批量查询(issue #25)。"""

from __future__ import annotations

from sites.animadex import batch_search, facets, search

from fakes import FakeHttp


def _item(slug):
    return {"slug": slug, "name": slug.replace("_", " "), "image": f"https://animadex.net/img/{slug}.jpg"}


class TestSearch:
    def test_params_and_parsing(self):
        http = FakeHttp()
        http.json_responses["https://animadex.net/api/characters/search"] = {
            "results": [_item("saber")], "total": 42,
        }
        results, total = search(http, "characters", query="saber", page=2, sort="count")
        url, params, _ = http.json_calls[-1]
        assert url == "https://animadex.net/api/characters/search"
        assert params["q"] == "saber"
        assert params["page"] == 2
        assert params["sort"] == "count"
        assert results[0]["slug"] == "saber"
        assert total == 42

    def test_filters_passed(self):
        http = FakeHttp()
        http.json_responses["https://animadex.net/api/artists/search"] = {"results": [], "total": 0}
        search(http, "artists", query="ask", filters={"hair_color": "blonde", "cat": "x"})
        params = http.json_calls[-1][1]
        assert params["hair_color"] == "blonde"  # 单选值原样传递
        assert params["cat"] == "x"

    def test_error_returns_empty(self):
        http = FakeHttp()  # 无 canned → TransportError → 空
        results, total = search(http, "characters")
        assert results == [] and total == 0


class TestBatch:
    def test_merges_and_dedupes(self):
        http = FakeHttp()
        http.json_responses["https://animadex.net/api/characters/search"] = {
            "results": [_item("a"), _item("b")], "total": 10,
        }
        results, total = batch_search(http, "characters", ["a", "b"])
        assert [r["slug"] for r in results] == ["a", "b"]  # 合并去重
        assert total == 20
        assert len(http.json_calls) == 2


class TestFacets:
    def test_returns_facets(self):
        # 实测结构:{key: {label, total, values: [{value, label, count}]}}
        http = FakeHttp()
        http.json_responses["https://animadex.net/api/characters/facets"] = {
            "facets": {"hair_color": {"label": "Hair Color", "total": 2,
                                       "values": [{"value": "blonde", "label": "Blonde", "count": 1}]}},
        }
        assert facets(http, "characters")["hair_color"]["values"][0]["value"] == "blonde"

    def test_single_facet_value_passed_raw(self):
        # 实测 API 忽略逗号合并值;筛选 UI 单选,值原样传递
        http = FakeHttp()
        http.json_responses["https://animadex.net/api/characters/search"] = {"results": [], "total": 0}
        search(http, "characters", query="saber", filters={"hair_color": "blonde"})
        params = http.json_calls[-1][1]
        assert params["hair_color"] == "blonde"
