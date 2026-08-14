"""中文别名索引:tags_enhanced.csv(名称, cn_name, wiki, post_count, category, nsfw)。

惰性加载 + 内存缓存;中文短语包含匹配,post_count 降序。
数据首次使用时从 Anima 包(ComfyUI-Danbooru-Anima-Prompt)复制到本项目
data/(gitignore);源缺失时优雅降级(空候选,不报错)。
"""

from __future__ import annotations

import csv
import io
import os
import shutil

DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "tags_enhanced.csv",
)
SOURCE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # custom_nodes 根
    "ComfyUI-Danbooru-Anima-Prompt",
    "tags_enhanced.csv",
)

_index: dict[str, list[tuple[str, int]]] | None = None  # 中文别名 → [(英文标签, post_count)]


def is_chinese_query(query: str) -> bool:
    """是否含 CJK 汉字(emoji/全角标点不算,避免误入中文路径)。"""
    return any("㐀" <= c <= "䶿" or "一" <= c <= "鿿" for c in query)


def query_token(query: str) -> str:
    """补全用的词元:中文查询取最后一个空格分隔词(与前端 replace-last-word 一致)。"""
    return query.split()[-1] if is_chinese_query(query) else query


def ensure_data() -> bool:
    """确保数据文件存在;首次使用从 Anima 包复制。失败返回 False(降级)。"""
    if os.path.exists(DATA_PATH):
        return True
    if not os.path.exists(SOURCE_PATH):
        return False
    try:
        os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
        shutil.copy2(SOURCE_PATH, DATA_PATH)
        return True
    except OSError:
        return False


def build_index(path: str) -> dict[str, list[tuple[str, int]]]:
    """解析 CSV → 别名索引;跳过空别名与表头。

    源文件为 GB18030 编码(Anima 包,实测);兼容 utf-8 读取。
    """
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return {}
    index: dict[str, list[tuple[str, int]]] = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 4 or row[0] == "name":
            continue
        name, cn_name = row[0], row[1]
        try:
            count = int(row[3] or 0)
        except ValueError:
            count = 0
        for alias in cn_name.split(","):
            alias = alias.strip()
            if alias:
                index.setdefault(alias, []).append((name, count))
    return index


def get_index() -> dict[str, list[tuple[str, int]]] | None:
    global _index
    if _index is None:
        if not ensure_data():
            return None
        _index = build_index(DATA_PATH)
    return _index


def rank(index: dict[str, list[tuple[str, int]]], query: str, limit: int = 10) -> list[dict]:
    """中文包含匹配:同一标签多别名命中取 post_count 最高者,降序取前 limit。"""
    hits: dict[str, tuple[str, int]] = {}  # tag → (命中的中文别名, post_count)
    for alias, entries in index.items():
        if query not in alias:
            continue
        for tag, count in entries:
            if tag not in hits or count > hits[tag][1]:
                hits[tag] = (alias, count)
    results = [{"tag": tag, "cn": cn, "post_count": n} for tag, (cn, n) in hits.items()]
    results.sort(key=lambda r: r["post_count"], reverse=True)
    return results[:limit]


def match(query: str, limit: int = 10) -> list[dict]:
    """中文查询入口:数据缺失时返回空候选(优雅降级)。"""
    index = get_index()
    if index is None:
        return []
    return rank(index, query, limit)
