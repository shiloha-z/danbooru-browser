"""Bounded disk cache for downloaded images (T8).

URL-keyed (hash of the download URL → file name), LRU eviction by mtime,
capacity in total bytes. Thread-safe enough for the browser's fetch path.
"""

from __future__ import annotations

import hashlib
import os
import threading
import urllib.parse
from pathlib import Path

DEFAULT_MAX_BYTES = 256 * 1024 * 1024  # 256MB


class DiskImageCache:
    def __init__(self, cache_dir: str, max_bytes: int = DEFAULT_MAX_BYTES):
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]
        ext = os.path.splitext(urllib.parse.urlparse(key).path)[1] or ".img"
        return self._dir / f"{digest}{ext}"

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        with self._lock:
            if path.is_file():
                try:
                    os.utime(path)  # LRU:访问刷新淘汰顺序
                except OSError:
                    pass
                return path.read_bytes()
        return None

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        with self._lock:
            # 原子写入:先写临时文件再替换,进程中断不会留下截断条目
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)
            self._evict()

    def _evict(self) -> None:
        files = [p for p in self._dir.iterdir() if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        if total <= self._max_bytes:
            return
        for p in sorted(files, key=lambda p: p.stat().st_mtime):  # 最旧先淘汰
            if total <= self._max_bytes:
                break
            total -= p.stat().st_size
            p.unlink(missing_ok=True)
