
"""
IncrementalIndexer
==================

Tracks which files have changed since the last index run using MD5 hashes.

Improvements over v1:
  - Persistent cache (JSON on disk) — survives server restarts
  - Batch-changed check: returns all changed files in one pass
  - Reports which files are new / modified / deleted
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class IncrementalIndexer:
    """
    Parameters
    ----------
    cache_dir : str | None
        Directory where the hash cache JSON is stored.
        Pass None to run in-memory only (cache is lost on restart).
    """

    CACHE_FILENAME = "file_hashes.json"

    def __init__(self, cache_dir: str | None = None):
        self.cache_dir  = cache_dir
        self._cache: dict[str, str] = {}

        if cache_dir:
            self._load()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def changed(self, path: str) -> bool:
        """
        Return True if *path* has changed since the last call to this method.
        Updates the internal cache (and persists it if cache_dir is set).
        """
        current = self._hash_file(path)
        if current is None:
            return False

        previous = self._cache.get(path)
        self._cache[path] = current

        return current != previous

    def filter_changed(self, paths: list[str]) -> list[str]:
        """
        Return only the paths that have changed (or are new) since last run.
        Updates the cache for ALL paths, not just changed ones.
        """
        changed: list[str] = []
        for path in paths:
            current = self._hash_file(path)
            if current is None:
                continue
            if self._cache.get(path) != current:
                changed.append(path)
            self._cache[path] = current

        self._save()
        return changed

    def deleted_files(self, known_paths: list[str]) -> list[str]:
        """
        Return paths that were in the cache but are no longer present on disk.
        Removes them from the cache.
        """
        known_set = set(known_paths)
        deleted   = [p for p in list(self._cache.keys()) if p not in known_set]
        for p in deleted:
            del self._cache[p]
        if deleted:
            self._save()
        return deleted

    def mark_indexed(self, path: str) -> None:
        """Explicitly mark a file as indexed at its current hash."""
        h = self._hash_file(path)
        if h:
            self._cache[path] = h

    def invalidate(self, path: str) -> None:
        """Force *path* to be re-indexed next time filter_changed is called."""
        self._cache.pop(path, None)

    def clear(self) -> None:
        """Reset the entire cache (forces full re-index on next run)."""
        self._cache.clear()
        self._save()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _hash_file(path: str) -> str | None:
        try:
            data = Path(path).read_bytes()
            return hashlib.md5(data).hexdigest()
        except Exception:
            return None

    def _cache_path(self) -> str:
        return os.path.join(self.cache_dir, self.CACHE_FILENAME)

    def _load(self) -> None:
        p = self._cache_path()
        if not os.path.exists(p):
            return
        try:
            with open(p, encoding="utf-8") as f:
                self._cache = json.load(f)
            logger.debug(f"IncrementalIndexer: loaded {len(self._cache)} cached hashes.")
        except Exception as exc:
            logger.warning(f"IncrementalIndexer: failed to load cache: {exc}")
            self._cache = {}

    def _save(self) -> None:
        if not self.cache_dir:
            return
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
        try:
            with open(self._cache_path(), "w", encoding="utf-8") as f:
                json.dump(self._cache, f)
        except Exception as exc:
            logger.warning(f"IncrementalIndexer: failed to save cache: {exc}")
