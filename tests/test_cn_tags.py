"""中文别名索引:解析、包含匹配、排序、降级(issue #23)。"""

from __future__ import annotations

import csv

from sites import cn_tags


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "cn_name", "wiki", "post_count", "category", "nsfw"])
        w.writerows(rows)


class TestRank:
    def test_contains_match_sorted_by_post_count(self, tmp_path):
        path = str(tmp_path / "tags.csv")
        write_csv(path, [
            ["1girl", "少女,女孩", "x", "7903062", "0", "0"],
            ["1girl_solo", "少女,单人少女", "x", "1000", "0", "0"],
            ["long_hair", "长发,长头发", "x", "5819139", "0", "0"],
        ])
        index = cn_tags.build_index(path)
        hits = cn_tags.rank(index, "少女", limit=10)
        assert [h["tag"] for h in hits] == ["1girl", "1girl_solo"]  # post_count 降序
        assert hits[0]["cn"] == "少女"  # 命中的别名用于展示
        hits2 = cn_tags.rank(index, "头发", limit=10)
        assert [h["tag"] for h in hits2] == ["long_hair"]

    def test_no_match_returns_empty(self, tmp_path):
        path = str(tmp_path / "tags.csv")
        write_csv(path, [["1girl", "少女", "x", "1", "0", "0"]])
        assert cn_tags.rank(cn_tags.build_index(path), "猫娘", limit=10) == []

    def test_limit(self, tmp_path):
        path = str(tmp_path / "tags.csv")
        write_csv(path, [
            ["a", "猫", "x", "3", "0", "0"],
            ["b", "猫娘", "x", "2", "0", "0"],
            ["c", "猫耳", "x", "1", "0", "0"],
        ])
        hits = cn_tags.rank(cn_tags.build_index(path), "猫", limit=2)
        assert len(hits) == 2
        assert [h["tag"] for h in hits] == ["a", "b"]

    def test_empty_aliases_skipped(self, tmp_path):
        path = str(tmp_path / "tags.csv")
        write_csv(path, [["1girl", " ,少女,", "x", "1", "0", "0"]])
        index = cn_tags.build_index(path)
        assert cn_tags.rank(index, "少女") != []
        assert cn_tags.rank(index, " ") == []


class TestDegradation:
    def test_missing_source_and_data_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cn_tags, "DATA_PATH", str(tmp_path / "data" / "tags.csv"))
        monkeypatch.setattr(cn_tags, "SOURCE_PATH", str(tmp_path / "src" / "tags.csv"))
        assert cn_tags.match("少女") == []  # 数据缺失 → 空候选,不报错

    def test_copies_from_source_on_first_use(self, monkeypatch, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        write_csv(str(src / "tags.csv"), [["1girl", "少女", "x", "1", "0", "0"]])
        data = tmp_path / "data" / "tags.csv"
        monkeypatch.setattr(cn_tags, "DATA_PATH", str(data))
        monkeypatch.setattr(cn_tags, "SOURCE_PATH", str(src / "tags.csv"))
        assert cn_tags.match("少女") == [{"tag": "1girl", "cn": "少女", "post_count": 1}]
        assert data.exists()  # 已复制

    def test_is_chinese_query(self):
        assert cn_tags.is_chinese_query("少女")
        assert not cn_tags.is_chinese_query("1girl")
        assert not cn_tags.is_chinese_query("1girl solo")
        assert not cn_tags.is_chinese_query("1girl 🐱")  # emoji 不算
        assert not cn_tags.is_chinese_query("，。！")  # 全角标点不算

    def test_query_token_takes_last_word_for_chinese(self):
        assert cn_tags.query_token("金发 少女") == "少女"
        assert cn_tags.query_token("1girl solo") == "1girl solo"  # 英文保持原样
