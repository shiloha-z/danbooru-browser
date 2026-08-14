"""HTTP adapter helpers: the image proxy allowlist is a security boundary."""

from __future__ import annotations

import pytest

from sites.http import is_allowed_image_url


class TestIsAllowedImageUrl:
    def test_allows_site_cdn(self):
        assert is_allowed_image_url("https://cdn.donmai.us/180x180/ab/cd/abcd.jpg")

    def test_allows_main_domain(self):
        assert is_allowed_image_url("https://danbooru.donmai.us/data/ab/cd/abcd.jpg")

    def test_rejects_other_hosts(self):
        assert not is_allowed_image_url("https://evil.example.com/x.jpg")
        assert not is_allowed_image_url("http://cdn.donmai.us/x.jpg")  # 非 https

    def test_rejects_non_http(self):
        assert not is_allowed_image_url("file:///etc/passwd")
        assert not is_allowed_image_url("javascript:alert(1)")

    def test_rejects_malformed(self):
        assert not is_allowed_image_url("")
        assert not is_allowed_image_url("cdn.donmai.us/relative.jpg")
