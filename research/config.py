"""Loads .env and config/research_config.yaml into a single Config object."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class Config:
    raw: dict[str, Any] = field(repr=False)

    @property
    def db_path(self) -> Path:
        return PROJECT_ROOT / self.raw["paths"]["db_path"]

    @property
    def keyword_pool_path(self) -> Path:
        return PROJECT_ROOT / self.raw["paths"]["keyword_pool_path"]

    @property
    def reports_dir(self) -> Path:
        return PROJECT_ROOT / self.raw["paths"]["reports_dir"]

    @property
    def oauth_token_path(self) -> Path:
        return PROJECT_ROOT / self.raw["paths"]["oauth_token_path"]

    @property
    def assets_dir(self) -> Path:
        return PROJECT_ROOT / self.raw["paths"]["assets_dir"]

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.raw
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    @property
    def youtube_api_key(self) -> str | None:
        return os.environ.get("YOUTUBE_API_KEY")

    @property
    def youtube_client_id(self) -> str | None:
        return os.environ.get("YOUTUBE_CLIENT_ID")

    @property
    def youtube_client_secret(self) -> str | None:
        return os.environ.get("YOUTUBE_CLIENT_SECRET")

    @property
    def gemini_api_key(self) -> str | None:
        return os.environ.get("GEMINI_API_KEY") or self.youtube_api_key


_config: Config | None = None


def load_config(path: Path | None = None) -> Config:
    global _config
    if _config is not None and path is None:
        return _config
    config_path = path or (PROJECT_ROOT / "config" / "research_config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    cfg = Config(raw=raw)
    if path is None:
        _config = cfg
    return cfg
