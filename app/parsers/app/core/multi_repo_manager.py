
"""
MultiRepoManager
================

Manages Smart-MCP indexes for **multiple repositories** simultaneously.

Use-cases:
  - Monorepos with distinct sub-projects (frontend + backend + shared lib)
  - Microservice setups where you want cross-repo search
  - Agency workflows working on several client codebases

Stored in the MCP tool registry alongside the primary retriever.
Exposed via the `list_repos` and `search_all_repos` MCP tools.

Architecture:
    {
        "api":       HybridRetriever(…),   # indexed at /projects/api
        "frontend":  HybridRetriever(…),   # indexed at /projects/frontend
        "shared":    HybridRetriever(…),   # indexed at /projects/shared
    }

search_all_repos() merges results across all repos and re-ranks with RRF.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class MultiRepoManager:
    """
    Manages multiple HybridRetriever instances keyed by a short repo name.
    """

    def __init__(self):
        # {repo_name: {"retriever": HybridRetriever, "path": str, "meta": dict}}
        self._repos: dict[str, dict] = {}

    # ------------------------------------------------------------------ #
    # Registration                                                         #
    # ------------------------------------------------------------------ #

    def add_repo(
        self,
        name: str,
        retriever,
        repo_path: str,
        meta: Optional[dict] = None,
    ) -> None:
        """Register an already-built retriever under *name*."""
        self._repos[name] = {
            "retriever": retriever,
            "path":      repo_path,
            "meta":      meta or {},
        }
        logger.info(f"MultiRepoManager: registered repo '{name}' → {repo_path}")

    def remove_repo(self, name: str) -> bool:
        """Unregister a repo. Returns True if it existed."""
        if name in self._repos:
            del self._repos[name]
            return True
        return False

    def index_new_repo(
        self,
        name: str,
        repo_path: str,
        cache_dir: Optional[str] = None,
        force_reindex: bool = False,
    ) -> None:
        """
        Index a new repository on-the-fly and register it.

        This builds a fresh SmartMCP index for *repo_path* and registers it
        under *name* so it appears in multi-repo searches immediately.
        """
        from app.main import SmartMCP
        cache = cache_dir or os.path.join(repo_path, ".smart-mcp-cache")
        logger.info(f"MultiRepoManager: indexing '{name}' → {repo_path} …")
        app = SmartMCP(repo_path, cache_dir=cache, force_reindex=force_reindex)
        app.build_index()

        # Retrieve the freshly registered retriever from the tool registry
        from app.mcp.tools import _RETRIEVER, _ROUTES, _INDEX_META
        if _RETRIEVER is not None:
            self.add_repo(name, _RETRIEVER, repo_path, _INDEX_META)

    # ------------------------------------------------------------------ #
    # Query                                                                #
    # ------------------------------------------------------------------ #

    def list_repos(self) -> list[dict]:
        """Return metadata for all registered repos."""
        result = []
        for name, entry in self._repos.items():
            r         = entry["retriever"]
            stats     = r.stats() if r else {}
            result.append({
                "name":          name,
                "path":          entry["path"],
                "chunk_count":   stats.get("total_chunks", 0),
                "unique_files":  stats.get("unique_files", 0),
                "framework":     entry["meta"].get("framework", "unknown"),
                "indexed_at":    entry["meta"].get("indexed_at", "unknown"),
            })
        return result

    def search_all(
        self,
        query: str,
        top_k: int = 8,
        repo_filter: str = "",
    ) -> list[dict]:
        """
        Search across all registered repos and merge results with RRF.

        Parameters
        ----------
        query       : the search query
        top_k       : total results to return across all repos
        repo_filter : if set, only search repos whose name contains this string
        """
        if not self._repos:
            return []

        repos_to_search = {
            name: entry for name, entry in self._repos.items()
            if not repo_filter or repo_filter.lower() in name.lower()
        }

        per_repo_results: list[list[dict]] = []
        for name, entry in repos_to_search.items():
            r = entry["retriever"]
            if r is None:
                continue
            try:
                results = r.search(query=query, top_k=top_k)
                # Tag each result with the repo name
                for res in results:
                    res["repo"] = name
                per_repo_results.append(results)
            except Exception as exc:
                logger.warning(f"Search failed for repo '{name}': {exc}")

        if not per_repo_results:
            return []

        return self._rrf_merge_cross_repo(per_repo_results, top_k)

    def get_retriever(self, name: str):
        """Return the retriever for a named repo, or None."""
        entry = self._repos.get(name)
        return entry["retriever"] if entry else None

    def __len__(self) -> int:
        return len(self._repos)

    def __contains__(self, name: str) -> bool:
        return name in self._repos

    # ------------------------------------------------------------------ #
    # Internal: cross-repo RRF                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _rrf_merge_cross_repo(
        per_repo_results: list[list[dict]],
        top_k: int,
        k: int = 60,
    ) -> list[dict]:
        """RRF merge across multiple ranked lists (one per repo)."""
        rrf_scores: dict[str, float] = {}
        all_docs:   dict[str, dict]  = {}

        for ranked_list in per_repo_results:
            for rank, result in enumerate(ranked_list):
                doc_id = result.get("id", "")
                if not doc_id:
                    continue
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
                all_docs[doc_id]   = result

        sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)
        results = []
        for doc_id in sorted_ids[:top_k]:
            doc = all_docs[doc_id].copy()
            doc["score"] = round(rrf_scores[doc_id], 6)
            results.append(doc)

        return results
