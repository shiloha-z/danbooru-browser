"""HTTP adapter helpers: the image proxy allowlist is a security boundary."""

from __future__ import annotations

import pytest

from sites.http import image_content_type, is_allowed_image_url, proxy_config, referer_for


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


class TestImageContentType:
    def test_known_extensions(self):
        assert image_content_type("https://cdn.donmai.us/x/1.jpg") == "image/jpeg"
        assert image_content_type("https://cdn.donmai.us/x/1.jpeg") == "image/jpeg"
        assert image_content_type("https://cdn.donmai.us/x/1.png") == "image/png"
        assert image_content_type("https://cdn.donmai.us/x/1.gif") == "image/gif"
        assert image_content_type("https://cdn.donmai.us/x/1.webp") == "image/webp"

    def test_unknown_extension_falls_back(self):
        assert image_content_type("https://cdn.donmai.us/x/1.webm") == "application/octet-stream"
        assert image_content_type("https://cdn.donmai.us/x/noext") == "application/octet-stream"


class TestRefererFor:
    def test_gelbooru_hosts_get_referer(self):
        assert referer_for("https://img4.gelbooru.com/images/x/y.png") == "https://gelbooru.com/"
        assert referer_for("https://gelbooru.com/index.php") == "https://gelbooru.com/"

    def test_other_hosts_no_referer(self):
        assert referer_for("https://cdn.donmai.us/x.jpg") is None
        assert referer_for("https://evil.example.com/x.jpg") is None


class TestProxyConfig:
    def test_empty_means_system_proxy(self):
        assert proxy_config("") is None
        assert proxy_config("   ") is None

    def test_host_port_gets_http_scheme(self):
        assert proxy_config("127.0.0.1:7897") == {
            "http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897",
        }

    def test_full_url_kept(self):
        assert proxy_config("http://proxy.example:8080") == {
            "http": "http://proxy.example:8080", "https": "http://proxy.example:8080",
        }

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            proxy_config("http://")  # 无 host
        with pytest.raises(ValueError):
            proxy_config("ftp://host:21")  # 非 http/https
        with pytest.raises(ValueError):
            proxy_config("socks5://host:1080")  # 仅支持 http/https
