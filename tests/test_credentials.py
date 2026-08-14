"""Local credentials: save/merge and per-site auth wiring (issue #5)."""

from __future__ import annotations

import json

import pytest

from sites import credentials as cred_mod


@pytest.fixture
def cred_file(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setattr(cred_mod, "_CONFIG_PATH", str(path))
    return path


class TestSaveCredentials:
    def test_save_creates_file(self, cred_file):
        cred_mod.save_credentials("gelbooru", {"user_id": "1", "api_key": "k1"})
        data = json.loads(cred_file.read_text(encoding="utf-8"))
        assert data["gelbooru"] == {"user_id": "1", "api_key": "k1"}
        assert cred_mod.get_credentials("gelbooru") == {"user_id": "1", "api_key": "k1"}

    def test_save_merges_non_empty_fields_only(self, cred_file):
        cred_mod.save_credentials("gelbooru", {"user_id": "1", "api_key": "k1"})
        cred_mod.save_credentials("gelbooru", {"user_id": "2", "api_key": ""})  # 空字段保持
        assert cred_mod.get_credentials("gelbooru") == {"user_id": "2", "api_key": "k1"}

    def test_multiple_sites_coexist(self, cred_file):
        cred_mod.save_credentials("danbooru", {"login": "u", "api_key": "k"})
        cred_mod.save_credentials("gelbooru", {"user_id": "1", "api_key": "k"})
        assert cred_mod.get_credentials("danbooru")["login"] == "u"
        assert cred_mod.get_credentials("gelbooru")["user_id"] == "1"

    def test_clear_removes_site_entry(self, cred_file):
        cred_mod.save_credentials("danbooru", {"login": "u", "api_key": "k"})
        cred_mod.save_credentials("gelbooru", {"user_id": "1", "api_key": "k"})
        cred_mod.clear_credentials("danbooru")
        assert cred_mod.get_credentials("danbooru") is None
        assert cred_mod.get_credentials("gelbooru")["user_id"] == "1"  # 其他站点不受影响
