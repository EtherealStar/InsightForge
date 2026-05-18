"""RSS and crawler source configuration helpers."""
from __future__ import annotations

import json
import os
from pathlib import Path


DATA_DIR = Path(os.getcwd()) / "data"
FEEDS_CONFIG_PATH = DATA_DIR / "feeds_config.json"
SITES_CONFIG_PATH = DATA_DIR / "sites_config.json"


def load_feeds() -> list[dict]:
    """Load configured RSS feeds, falling back to AppConfig defaults."""
    if FEEDS_CONFIG_PATH.exists():
        with FEEDS_CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)

    from core.config_manager import get_config_manager

    config = get_config_manager().config
    return list(config.rss_feeds)


def save_feeds(feeds: list[dict]) -> None:
    """Persist RSS feed configuration."""
    FEEDS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FEEDS_CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(feeds, f, ensure_ascii=False, indent=2)


def load_sites() -> list[dict]:
    """Load configured crawler sites."""
    if SITES_CONFIG_PATH.exists():
        with SITES_CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_sites(sites: list[dict]) -> None:
    """Persist crawler site configuration."""
    SITES_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SITES_CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)
