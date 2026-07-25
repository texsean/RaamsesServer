"""Site configuration — unique SiteId for each RAAMSES installation.

The SiteId is generated once on first use and persisted to a config file.
It identifies this specific RAAMSES installation in protocol messages,
issue reports, and verification responses.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Default location for the persisted site identity
_DEFAULT_CONFIG_DIR = Path.home() / ".raamses"
_DEFAULT_CONFIG_FILE = _DEFAULT_CONFIG_DIR / "site.json"

# Environment variable override (useful for testing or multi-instance setups)
_ENV_CONFIG_PATH = "RAAMSES_SITE_CONFIG"


class SiteConfig:
    """Manages the persistent site identity for this RAAMSES installation.

    The SiteId is a random UUID generated on first access and saved to
    ~/.raamses/site.json (or the path specified by RAAMSES_SITE_CONFIG).

    Fields:
        site_id:       Unique UUID identifying this installation
        hostname:      Machine hostname at creation time
        created_at:    ISO 8601 UTC timestamp of first creation
        install_path:  Filesystem path where the installation lives
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        env_path = os.environ.get(_ENV_CONFIG_PATH)
        if config_path:
            self._config_path = Path(config_path)
        elif env_path:
            self._config_path = Path(env_path)
        else:
            self._config_path = _DEFAULT_CONFIG_FILE

        self._data: Optional[dict] = None

    @property
    def config_path(self) -> Path:
        return self._config_path

    def _load(self) -> dict:
        """Load site config from disk, or create it if missing."""
        if self._data is not None:
            return self._data

        if self._config_path.exists():
            try:
                with open(self._config_path, "r") as f:
                    data: dict = json.load(f)
                    self._data = data
                    return data
            except (json.JSONDecodeError, OSError):
                pass  # fall through to create

        # Generate new site identity
        data = {
            "site_id": str(uuid.uuid4()),
            "hostname": os.uname().nodename if hasattr(os, "uname") else "unknown",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "install_path": str(Path.cwd()),
        }
        self._data = data

        # Persist
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._config_path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(str(tmp_path), str(self._config_path))

        return data

    @property
    def site_id(self) -> str:
        """Return the unique site ID for this installation."""
        return self._load()["site_id"]

    @property
    def hostname(self) -> str:
        return self._load().get("hostname", "unknown")

    @property
    def created_at(self) -> str:
        return self._load().get("created_at", "")

    @property
    def install_path(self) -> str:
        return self._load().get("install_path", "")

    def to_dict(self) -> dict:
        """Return all site config fields as a dict."""
        return dict(self._load())

    def refresh(self) -> None:
        """Force a re-read from disk (clears the in-memory cache)."""
        self._data = None


# Singleton convenience accessor
_site_config: Optional[SiteConfig] = None


def get_site_config() -> SiteConfig:
    """Return the global SiteConfig singleton."""
    global _site_config
    if _site_config is None:
        _site_config = SiteConfig()
    return _site_config


def get_site_id() -> str:
    """Convenience: return just the site ID string."""
    return get_site_config().site_id