
"""
RepoSummarizer
==============

Generates a structured, token-efficient overview of an indexed codebase.

The summary is designed as an AI-first document: it gives the AI agent
exactly the "lay of the land" it needs to navigate the repo intelligently,
without loading a single source file.

Output structure:
    {
        "repo_path":      "/path/to/repo",
        "framework":      "django",
        "language":       "python",
        "totals":         {files, functions, classes, methods, routes},
        "by_language":    {"python": {files, symbols}, …},
        "top_files":      [most-referenced / largest files],
        "entry_points":   [main, wsgi, asgi, app.py, server.py, …],
        "key_modules":    [top-level packages discovered],
        "models":         [model class names for Django/SQLAlchemy],
        "serializers":    [{serializer, model, file, line}],
        "routes_summary": {total, by_method: {GET: N, POST: N, …}},
        "hot_symbols":    [most-called symbols by graph in-degree],
        "dead_symbols":   [count of unreferenced symbols],
        "index_health":   {chunk_count, unique_files, graph_edges},
    }

Token cost: ~300–600 tokens  (compared to 500K–1M for reading the whole repo).
"""

from __future__ import annotations

import logging
import os
from collections import Counter, defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class RepoSummarizer:
    """
    Parameters
    ----------
    retriever   : HybridRetriever instance (already built)
    routes      : list[dict] from RouteMapper
    meta        : dict from SmartMCP._register
    """

    def __init__(self, retriever, routes: list, meta: dict):
        self._retriever = retriever
        self._routes    = routes or []
        self._meta      = meta or {}

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def summarize(self) -> dict:
        """Return the full repository summary dict."""
        chunks    = self._retriever.documents
        repo_path = self._meta.get("repo_path", "")

        totals         = self._compute_totals(chunks)
        by_language    = self._by_language(chunks)
        top_files      = self._top_files(chunks)
        entry_points   = self._find_entry_points(repo_path)
        key_modules    = self._key_modules(chunks)
        models         = self._find_models(chunks)
        serializers    = self._find_serializers(chunks)
        routes_summary = self._routes_summary()
        hot_symbols    = self._hot_symbols()
        dead_count     = self._dead_symbol_count()
        index_health   = self._index_health(chunks)

        return {
            "repo_path":      repo_path,
            "framework":      self._meta.get("framework", "unknown"),
            "language":       self._meta.get("language", "unknown"),
            "indexed_at":     self._meta.get("indexed_at", "unknown"),
            "totals":         totals,
            "by_language":    by_language,
            "top_files":      top_files,
            "entry_points":   entry_points,
            "key_modules":    key_modules,
            "models":         models,
            "serializers":    serializers,
            "routes_summary": routes_summary,
            "hot_symbols":    hot_symbols,
            "dead_symbols":   dead_count,
            "index_health":   index_health,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _compute_totals(self, chunks: list[dict]) -> dict:
        type_counts: Counter = Counter(c.get("type", "unknown") for c in chunks)
        files = len({c.get("file", "") for c in chunks})
        return {
            "indexed_chunks":  len(chunks),
            "unique_files":    files,
            "functions":       type_counts.get("function", 0)
                             + type_counts.get("async_function", 0),
            "methods":         type_counts.get("method", 0)
                             + type_counts.get("async_method", 0),
            "classes":         type_counts.get("class", 0),
            "routes":          len(self._routes),
            "async_functions": type_counts.get("async_function", 0),
        }

    def _by_language(self, chunks: list[dict]) -> dict:
        lang_map: dict[str, dict] = defaultdict(lambda: {"files": set(), "symbols": 0})
        ext_to_lang = {
            ".py": "python", ".ts": "typescript", ".tsx": "typescript",
            ".js": "javascript", ".jsx": "javascript", ".dart": "dart",
            ".go": "go", ".java": "java", ".kt": "kotlin",
            ".rs": "rust", ".rb": "ruby", ".php": "php",
            ".cs": "csharp", ".swift": "swift",
        }
        for chunk in chunks:
            ext  = Path(chunk.get("file", "")).suffix.lower()
            lang = ext_to_lang.get(ext, "other")
            lang_map[lang]["files"].add(chunk.get("file", ""))
            lang_map[lang]["symbols"] += 1

        return {
            lang: {"files": len(v["files"]), "symbols": v["symbols"]}
            for lang, v in sorted(lang_map.items(), key=lambda x: -x[1]["symbols"])
        }

    def _top_files(self, chunks: list[dict], limit: int = 10) -> list[dict]:
        file_counts: Counter = Counter(c.get("file", "") for c in chunks)
        result = []
        for file_path, count in file_counts.most_common(limit):
            result.append({
                "file":         file_path,
                "symbol_count": count,
                "basename":     Path(file_path).name,
            })
        return result

    def _find_entry_points(self, repo_path: str) -> list[str]:
        if not repo_path:
            return []
        entry_names = {
            "main.py", "app.py", "server.py", "wsgi.py", "asgi.py",
            "manage.py", "index.js", "index.ts", "server.js", "server.ts",
            "app.js", "app.ts", "main.go", "main.rs", "main.dart",
        }
        found = []
        try:
            root = Path(repo_path)
            for name in entry_names:
                for p in root.rglob(name):
                    # Only top-level or one level deep
                    rel = p.relative_to(root)
                    if len(rel.parts) <= 2:
                        found.append(str(p))
        except Exception:
            pass
        return found[:10]

    def _key_modules(self, chunks: list[dict], limit: int = 15) -> list[str]:
        """Identify top-level packages by looking at the first path component."""
        modules: Counter = Counter()
        for chunk in chunks:
            file = chunk.get("file", "")
            if not file:
                continue
            parts = Path(file).parts
            # Look for the first meaningful package name
            for part in parts:
                if (part.endswith(".py") or part.endswith(".ts") or
                        part.endswith(".js") or part.endswith(".go")):
                    break
                if part not in {".", "..", "src", "lib", "app", "pkg"}:
                    modules[part] += 1
                    break
        return [m for m, _ in modules.most_common(limit)]

    def _find_models(self, chunks: list[dict]) -> list[dict]:
        """Find Django Model, SQLAlchemy Base, TypeORM Entity classes."""
        model_bases = {
            "Model", "Base", "AbstractModel", "TimeStampedModel",
            "MPTTModel", "PolymorphicModel",  # Django
        }
        models = []
        for chunk in chunks:
            if chunk.get("type") != "class":
                continue
            bases = set(chunk.get("base_classes", []))
            if bases & model_bases:
                models.append({
                    "name": chunk.get("symbol", ""),
                    "file": chunk.get("file", ""),
                    "line": chunk.get("start_line", 0),
                    "base": list(bases & model_bases)[0] if bases & model_bases else "",
                })
        return models[:30]

    def _find_serializers(self, chunks: list[dict]) -> list[dict]:
        """Find DRF serializers already annotated in chunks."""
        serializers = []
        for chunk in chunks:
            if chunk.get("type") != "class":
                continue
            name = chunk.get("symbol", "")
            if "Serializer" in name:
                serializers.append({
                    "name": name,
                    "file": chunk.get("file", ""),
                    "line": chunk.get("start_line", 0),
                })
        return serializers[:30]

    def _routes_summary(self) -> dict:
        method_counts: Counter = Counter()
        for route in self._routes:
            method = route.get("method", "UNKNOWN").upper()
            method_counts[method] += 1
        return {
            "total":     len(self._routes),
            "by_method": dict(method_counts),
        }

    def _hot_symbols(self, limit: int = 10) -> list[dict]:
        """Return symbols with highest graph in-degree (most called)."""
        try:
            import networkx as nx
            G = self._retriever.graph
            if G is None or G.number_of_nodes() == 0:
                return []
            in_degrees = sorted(G.in_degree(), key=lambda x: x[1], reverse=True)
            hot = []
            for node_id, degree in in_degrees[:limit]:
                if degree == 0:
                    break
                chunk = self._retriever._id_to_chunk.get(node_id)
                if chunk:
                    hot.append({
                        "symbol":  chunk.get("symbol", ""),
                        "type":    chunk.get("type", ""),
                        "file":    chunk.get("file", ""),
                        "callers": degree,
                    })
            return hot
        except Exception:
            return []

    def _dead_symbol_count(self) -> int:
        try:
            dead = self._retriever.find_dead_code(limit=9999)
            return len(dead)
        except Exception:
            return 0

    def _index_health(self, chunks: list[dict]) -> dict:
        try:
            G = self._retriever.graph
            graph_edges = G.number_of_edges() if G else 0
        except Exception:
            graph_edges = 0
        return {
            "total_chunks": len(chunks),
            "graph_edges":  graph_edges,
            "model":        self._retriever.model_name,
            "cache_dir":    self._retriever.cache_dir or "in-memory",
        }
