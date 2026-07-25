"""Tests for site_config.py — Site ID generation and persistence."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from rgs.site_config import SiteConfig


class TestSiteConfig:
    """Test the SiteConfig class."""

    def test_generates_site_id_on_first_access(self, tmp_path):
        """Site ID should be generated on first access."""
        config = SiteConfig(config_path=tmp_path / "site.json")
        site_id = config.site_id
        assert site_id is not None
        assert len(site_id) == 36  # UUID format
        # Should contain hyphens (UUID format)
        assert "-" in site_id

    def test_persists_site_id_to_disk(self, tmp_path):
        """Site ID should be persisted to disk."""
        config_path = tmp_path / "site.json"
        config = SiteConfig(config_path=config_path)
        site_id = config.site_id

        # File should exist
        assert config_path.exists()

        # File should contain valid JSON with the site_id
        with open(config_path) as f:
            data = json.load(f)
        assert data["site_id"] == site_id
        assert "hostname" in data
        assert "created_at" in data
        assert "install_path" in data

    def test_same_site_id_on_reload(self, tmp_path):
        """Reloading from the same path should return the same site ID."""
        config_path = tmp_path / "site.json"

        config1 = SiteConfig(config_path=config_path)
        id1 = config1.site_id

        config2 = SiteConfig(config_path=config_path)
        id2 = config2.site_id

        assert id1 == id2

    def test_refresh_reloads_from_disk(self, tmp_path):
        """refresh() should clear the cache and re-read from disk."""
        config_path = tmp_path / "site.json"
        config = SiteConfig(config_path=config_path)
        id1 = config.site_id

        # Modify the file directly
        with open(config_path) as f:
            data = json.load(f)
        data["site_id"] = "modified-id"
        with open(config_path, "w") as f:
            json.dump(data, f)

        # Without refresh, we get the cached value
        assert config.site_id == id1

        # After refresh, we get the new value
        config.refresh()
        assert config.site_id == "modified-id"

    def test_to_dict_returns_all_fields(self, tmp_path):
        """to_dict() should return all site config fields."""
        config = SiteConfig(config_path=tmp_path / "site.json")
        d = config.to_dict()
        assert "site_id" in d
        assert "hostname" in d
        assert "created_at" in d
        assert "install_path" in d

    def test_env_var_override(self, tmp_path, monkeypatch):
        """RAAMSES_SITE_CONFIG env var should override the default path."""
        custom_path = tmp_path / "custom" / "site.json"
        monkeypatch.setenv("RAAMSES_SITE_CONFIG", str(custom_path))

        config = SiteConfig()
        site_id = config.site_id

        assert custom_path.exists()
        with open(custom_path) as f:
            data = json.load(f)
        assert data["site_id"] == site_id

    def test_different_paths_get_different_ids(self, tmp_path):
        """Different config paths should generate different site IDs."""
        config1 = SiteConfig(config_path=tmp_path / "site1.json")
        config2 = SiteConfig(config_path=tmp_path / "site2.json")

        assert config1.site_id != config2.site_id