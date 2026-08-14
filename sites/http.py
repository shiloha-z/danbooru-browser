"""HTTP adapter for the Site port (category 4: port + production adapter + test fake).

Production adapter throttles API calls (danbooru 匿名约 2 req/s); the tests
inject a fake HTTP client instead. `requests` is imported lazily so the core
test suite never needs it.
"""

from __future__ import annotations

import os
import threading
import time
import urllib.parse
from typing import Any, Iterator, Protocol

from core.errors import TransportError

# 面板图片代理只放行站点自己的 CDN 域名,防止把 ComfyUI 变成任意 URL 代理(SSRF)。
# 新站点接入时在此追加其图片域名。
IMAGE_HOST_ALLOWLIST = frozenset({
    "danbooru.donmai.us", "cdn.donmai.us",
    "gelbooru.com", "img2.gelbooru.com", "img3.gelbooru.com", "img4.gelbooru.com",
    "civitai.com", "image.civitai.com",
})

_IMAGE_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def is_allowed_image_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in IMAGE_HOST_ALLOWLIST


def image_content_type(url: str) -> str:
    """按 URL 扩展名返回图片 Content-Type;未知扩展名回退 octet-stream。"""
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    return _IMAGE_CONTENT_TYPES.get(ext, "application/octet-stream")


def referer_for(url: str) -> str | None:
    """热链保护 CDN 需要的 Referer;其余站点返回 None。

    gelbooru 的 CDN 对无 Referer 请求返回帖子 HTML 页(HTTP 200),
    带站点 Referer 才返回真实图片(2026-08 实测)。
    """
    host = urllib.parse.urlparse(url).hostname or ""
    if host == "gelbooru.com" or host.endswith(".gelbooru.com"):
        return "https://gelbooru.com/"
    return None


def proxy_config(proxy: str) -> dict[str, str] | None:
    """代理字符串 → requests proxies 配置;空 = None(系统代理)。非法值抛 ValueError。"""
    proxy = proxy.strip() if proxy else ""
    if not proxy:
        return None
    if "://" not in proxy:
        proxy = f"http://{proxy}"
    parsed = urllib.parse.urlparse(proxy)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"非法代理地址: {proxy!r}")
    return {"http": proxy, "https": proxy}


class HttpAdapter(Protocol):
    def get_json(self, url: str, params: dict[str, Any] | None = None,
                 auth: tuple[str, str] | None = None) -> Any: ...

    def get_bytes(self, url: str) -> bytes: ...

    def iter_bytes(self, url: str, chunk_size: int = 65536) -> Iterator[bytes]: ...

    def set_proxy(self, proxy: str) -> None: ...


class RequestsHttpAdapter:
    def __init__(self, min_interval: float = 0.6, timeout: float = 15.0):
        import requests  # noqa: PLC0415 — lazy: tests never need requests installed

        self._session = requests.Session()
        # danbooru 拒收 python-requests 默认 UA(403);应用 UA 不能带括号,否则同样 403(2026-08 实测)
        self._session.headers["User-Agent"] = "danbooru-browser-comfyui/0.1"
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
            raise TransportError(f"HTTP {resp.status_code}: {url}", status=resp.status_code)
        return resp

    def set_proxy(self, proxy: str) -> None:
        """设置全局代理(搜索/图片/补全共用);空值恢复系统代理(env/trust_env)。"""
        self._session.proxies = proxy_config(proxy) or {}

    def get_json(self, url: str, params: dict[str, Any] | None = None,
                 auth: tuple[str, str] | None = None) -> Any:
        self._throttle()  # API 调用限流;图片走 CDN,不限
        return self._check(self._session.get(url, params=params, timeout=self._timeout, auth=auth), url).json()

    def _headers_for(self, url: str) -> dict[str, str]:
        referer = referer_for(url)
        return {"Referer": referer} if referer else {}

    def get_bytes(self, url: str) -> bytes:
        return self._check(
            self._session.get(url, timeout=self._timeout * 2, headers=self._headers_for(url)), url
        ).content

    def iter_bytes(self, url: str, chunk_size: int = 65536) -> Iterator[bytes]:
        """流式读取:面板图片代理逐块转发用;响应校验在首个 chunk 前触发。"""
        resp = self._check(
            self._session.get(url, timeout=self._timeout * 2, stream=True, headers=self._headers_for(url)),
            url,
        )
        try:
            yield from resp.iter_content(chunk_size=chunk_size)
        finally:
            resp.close()  # 提前中断时也释放连接
