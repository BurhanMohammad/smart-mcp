
"""
Smart-MCP Configuration
=======================

Configuration is resolved in this priority order (highest wins):

  1. smart-mcp.config.json  in the repository root (project-level)
  2. smart-mcp.config.json  in the user home dir    (user-level)
  3. Environment variables  (e.g. SMART_MCP_MODEL)
  4. Built-in defaults      (defined in SmartMCPConfig below)

Drop a `smart-mcp.config.json` in your project root to customize.
Example:

    {
        "embedding_model":  "BAAI/bge-base-en-v1.5",
        "max_file_kb":      200,
        "top_k_default":    10,
        "excluded_dirs":    ["custom_vendor", "auto_generated"],
        "token_budget_default": 4000,
        "index_on_startup": true
    }
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config file name ─────────────────────────────────────────────────────── #
CONFIG_FILENAME = "smart-mcp.config.json"


@dataclass
class SmartMCPConfig:
    """
    All Smart-MCP configuration options with their defaults.

    Attributes
    ----------
    embedding_model     : SentenceTransformer model for dense embeddings.
    max_file_kb         : Skip files larger than this (default 500 KB).
    top_k_default       : Default number of results for search_context.
    token_budget_default: Default token budget for search_with_budget.
    excluded_dirs       : Additional dirs to exclude (merged with built-in set).
    index_on_startup    : Auto-index on server start (default True).
    cache_subdir        : Subdirectory name inside repo for persistent cache.
    min_symbol_length   : Skip symbols shorter than this (avoids noise).
    graph_depth_default : Default BFS depth for get_related.
    """

    embedding_model:      str       = "BAAI/bge-small-en-v1.5"
    max_file_kb:          int       = 500
    top_k_default:        int       = 8
    token_budget_default: int       = 3000
    excluded_dirs:        list[str] = field(default_factory=list)
    index_on_startup:     bool      = True
    cache_subdir:         str       = ".smart-mcp-cache"
    min_symbol_length:    int       = 2
    graph_depth_default:  int       = 1

    def as_dict(self) -> dict:
        return {
            "embedding_model":      self.embedding_model,
            "max_file_kb":          self.max_file_kb,
            "top_k_default":        self.top_k_default,
            "token_budget_default": self.token_budget_default,
            "excluded_dirs":        self.excluded_dirs,
            "index_on_startup":     self.index_on_startup,
            "cache_subdir":         self.cache_subdir,
            "min_symbol_length":    self.min_symbol_length,
            "graph_depth_default":  self.graph_depth_default,
        }


# ── Loader ───────────────────────────────────────────────────────────────── #

def load_config(repo_path: Optional[str] = None) -> SmartMCPConfig:
    """
    Load configuration by merging all sources (repo > home > env > defaults).
    """
    cfg = SmartMCPConfig()

    # 1. User-level config (~/.smart-mcp.config.json or ~/smart-mcp.config.json)
    home_candidates = [
        Path.home() / f".{CONFIG_FILENAME}",
        Path.home() / CONFIG_FILENAME,
    ]
    for p in home_candidates:
        if p.exists():
            _merge_from_file(cfg, str(p))
            break

    # 2. Repo-level config (repo_path/smart-mcp.config.json)
    if repo_path:
        repo_cfg = Path(repo_path) / CONFIG_FILENAME
        if repo_cfg.exists():
            _merge_from_file(cfg, str(repo_cfg))

    # 3. Environment variables
    _merge_from_env(cfg)

    logger.debug(f"Config loaded: {cfg.as_dict()}")
    return cfg


def _merge_from_file(cfg: SmartMCPConfig, path: str) -> None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _apply(cfg, data)
        logger.info(f"Config loaded from {path}")
    except Exception as exc:
        logger.warning(f"Could not load config from {path}: {exc}")


def _merge_from_env(cfg: SmartMCPConfig) -> None:
    env_map = {
        "SMART_MCP_MODEL":          ("embedding_model",      str),
        "SMART_MCP_MAX_FILE_KB":    ("max_file_kb",          int),
        "SMART_MCP_TOP_K":          ("top_k_default",        int),
        "SMART_MCP_TOKEN_BUDGET":   ("token_budget_default", int),
        "SMART_MCP_CACHE_SUBDIR":   ("cache_subdir",         str),
        "SMART_MCP_INDEX_ON_START": ("index_on_startup",     _bool),
    }
    for env_key, (attr, cast) in env_map.items():
        val = os.environ.get(env_key, "").strip()
        if val:
            try:
                setattr(cfg, attr, cast(val))
            except Exception:
                pass


def _apply(cfg: SmartMCPConfig, data: dict) -> None:
    for key, value in data.items():
        if hasattr(cfg, key):
            try:
                if key == "excluded_dirs" and isinstance(value, list):
                    cfg.excluded_dirs = list({*cfg.excluded_dirs, *value})
                else:
                    setattr(cfg, key, value)
            except Exception:
                pass


def _bool(v: str) -> bool:
    return v.lower() in {"1", "true", "yes", "on"}


# ── Default template writer ──────────────────────────────────────────────── #

def write_default_config(dest_dir: str) -> str:
    """
    Write a default smart-mcp.config.json to *dest_dir*.
    Returns the path of the written file.
    """
    cfg  = SmartMCPConfig()
    dest = Path(dest_dir) / CONFIG_FILENAME
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(cfg.as_dict(), f, indent=2)
    logger.info(f"Default config written to {dest}")
    return str(dest)


# ── Module-level singleton ────────────────────────────────────────────────── #
# Populated lazily; call load_config() to refresh.
_DEFAULT_CONFIG = SmartMCPConfig()
