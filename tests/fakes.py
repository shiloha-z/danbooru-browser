"""Test fakes for the core seam: fake HTTP client and in-memory image cache.

The Site port (category 4) is exercised through a fake HTTP adapter, so tests
never touch the network and never import comfy.
"""

from __future__ import annotations

from typing import Any

from core.errors import TransportError
from core.model import Post


class FakeHttp:
    """Canned HTTP client. Missing URLs raise TransportError, like the real adapter."""

    def __init__(self) -> None:
        self.json_responses: dict[str, Any] = {}
        self.bytes_responses: dict[str, bytes] = {}
        self.json_calls: list[tuple[str, dict[str, Any] | None]] = []
        self.bytes_calls: list[str] = []

    def get_json(self, url: str, params: dict[str, Any] | None = None,
                 auth: tuple[str, str] | None = None) -> Any:
        self.json_calls.append((url, params, auth))
        try:
            return self.json_responses[url]
        except KeyError:
            raise TransportError(f"no canned response for {url}") from None

    def get_bytes(self, url: str) -> bytes:
        self.bytes_calls.append(url)
        try:
            return self.bytes_responses[url]
        except KeyError:
            raise TransportError(f"no canned bytes for {url}") from None

    def iter_bytes(self, url: str, chunk_size: int = 65536):
        self.bytes_calls.append(url)
        try:
            data = self.bytes_responses[url]
        except KeyError:
            raise TransportError(f"no canned bytes for {url}") from None
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    def set_proxy(self, proxy: str) -> None:
        self.proxy = proxy


class MemoryCache:
    """In-memory ImageCache for cache tests."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.hits = 0

    def get(self, key: str) -> bytes | None:
        data = self.data.get(key)
        if data is not None:
            self.hits += 1
        return data

    def put(self, key: str, data: bytes) -> None:
        self.data[key] = data


def make_post(
    post_id: int,
    tags: tuple[str, ...] = ("1girl", "long_hair"),
    rating: str = "g",
    score: int = 10,
    author: str = "artist",
    file_ext: str = "jpg",
    animated: bool = False,
) -> Post:
    """A Post with a danbooru-shaped raw dict."""
    raw = {
        "id": post_id,
        "file_url": f"https://cdn.example/{post_id}.{file_ext}",
        "large_file_url": f"https://cdn.example/{post_id}_l.{file_ext}",
        "preview_file_url": f"https://cdn.example/{post_id}_p.jpg",
        "tag_string": " ".join(tags),
        "tag_string_artist": author,
        "rating": rating,
        "score": score,
        "file_ext": file_ext,
    }
    return Post(
        id=post_id,
        site="danbooru",
        file_url=raw["file_url"],
        sample_url=raw["large_file_url"],
        preview_url=raw["preview_file_url"],
        tags=tags,
        rating=rating,
        score=score,
        author=author,
        raw=raw,
        animated=animated,
    )


IMAGE_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"
