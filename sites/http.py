"""HTTP adapter for the Site port (category 4: port + production adapter + test fake).

Production adapter throttles API calls (danbooru 匿名约 2 req/s); the tests
inject a fake HTTP client instead. `requests` is imported lazily so the core
test suite never needs it.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Protocol

from core.errors import TransportError


class HttpAdapter(Protocol):
    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any: ...

    def get_bytes(self, url: str) -> bytes: ...


class RequestsHttpAdapter:
    def __init__(self, min_interval: float = 0.6, timeout: float = 15.0):
        import requests  # noqa: PLC0415 — lazy: tests never need requests installed

        self._session = requests.Session()
        self._min_interval = min_interval
        self._timeout = timeout
        self._lock = threading.Lock()
        self._last_request = 0.0

    def _throttle(self) -> None:
        with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    def _check(self, resp: Any, url: str):
        if resp.status_code != 200:
            raise TransportError(f"HTTP {resp.status_code}: {url}")
        return resp

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        self._throttle()  # API 调用限流;图片走 CDN,不限
        return self._check(self._session.get(url, params=params, timeout=self._timeout), url).json()

    def get_bytes(self, url: str) -> bytes:
        return self._check(self._session.get(url, timeout=self._timeout * 2), url).content
