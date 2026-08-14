"""Wiring: the shared Browser instance for routes and the executor node."""

from __future__ import annotations

import os

from core.browser import Browser
from core.disk_cache import DiskImageCache
from sites import build_registry
from sites.http import RequestsHttpAdapter

_adapter: RequestsHttpAdapter | None = None
_browser: Browser | None = None
_cache: DiskImageCache | None = None


def get_http() -> RequestsHttpAdapter:
    global _adapter
    if _adapter is None:
        _adapter = RequestsHttpAdapter()
    return _adapter


def get_cache() -> DiskImageCache:
    global _cache
    if _cache is None:
        _cache = DiskImageCache(os.path.join(os.path.dirname(__file__), "cache"))
    return _cache


def get_browser() -> Browser:
    global _browser
    if _browser is None:
        _browser = Browser(build_registry(get_http()), image_cache=get_cache())
    return _browser
