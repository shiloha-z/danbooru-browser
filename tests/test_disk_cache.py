"""Bounded disk cache: URL-keyed, LRU eviction (issue #4)."""

from __future__ import annotations

from core.disk_cache import DiskImageCache


class TestDiskImageCache:
    def test_put_get_roundtrip(self, tmp_path):
        cache = DiskImageCache(str(tmp_path))
        cache.put("https://cdn/x/1.jpg", b"\xff\xd8" * 10)
        assert cache.get("https://cdn/x/1.jpg") == b"\xff\xd8" * 10

    def test_get_missing_returns_none(self, tmp_path):
        assert DiskImageCache(str(tmp_path)).get("https://cdn/x/nope.jpg") is None

    def test_url_keyed(self, tmp_path):
        cache = DiskImageCache(str(tmp_path))
        cache.put("https://cdn/x/1.jpg", b"a")
        cache.put("https://cdn/x/2.jpg", b"b")
        assert cache.get("https://cdn/x/1.jpg") == b"a"
        assert cache.get("https://cdn/x/2.jpg") == b"b"

    def test_eviction_respects_budget(self, tmp_path):
        cache = DiskImageCache(str(tmp_path), max_bytes=100)
        for i in range(10):
            cache.put(f"https://cdn/x/{i}.jpg", bytes([i]) * 20)
        total = sum(p.stat().st_size for p in tmp_path.iterdir())
        assert total <= 100  # 有界:不无限增长

    def test_lru_access_refreshes_eviction_order(self, tmp_path):
        import os
        cache = DiskImageCache(str(tmp_path), max_bytes=120)  # 容纳 2 个 60B
        cache.put("https://cdn/x/old.jpg", b"o" * 60)
        cache.put("https://cdn/x/keep.jpg", b"k" * 60)
        # 显式把 keep 时间设旧:消除低分辨率文件系统(FAT32 2s)的 mtime 抖动
        keep_path = cache._path("https://cdn/x/keep.jpg")
        os.utime(keep_path, (1_000_000, 1_000_000))
        cache.get("https://cdn/x/old.jpg")  # 访问刷新到 now,晚于 keep 的旧时间
        cache.put("https://cdn/x/new.jpg", b"n" * 60)  # 第 3 个触发淘汰
        assert cache.get("https://cdn/x/keep.jpg") is None  # 未访问的被淘汰
        assert cache.get("https://cdn/x/old.jpg") == b"o" * 60  # 访问过的存活

    def test_reuses_directory(self, tmp_path):
        cache = DiskImageCache(str(tmp_path))
        cache.put("https://cdn/x/1.jpg", b"data")
        cache2 = DiskImageCache(str(tmp_path))  # 新实例复用同一目录
        assert cache2.get("https://cdn/x/1.jpg") == b"data"
