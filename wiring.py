"""Wiring: the shared Browser instance for routes and the executor node.

The image cache stays None for T1 (bounded disk cache lands with its own
ticket); every execution re-downloads the selected image.
"""

from __future__ import annotations

from core.browser import Browser
from sites import build_registry
from sites.http import RequestsHttpAdapter

_adapter: RequestsHttpAdapter | None = None
_browser: Browser | None = None


def get_http() -> RequestsHttpAdapter:
    global _adapter
    if _adapter is None:
        _adapter = RequestsHttpAdapter()
    return _adapter


def get_browser() -> Browser:
    global _browser
    if _browser is None:
        _browser = Browser(build_registry(get_http()))
    return _browser
