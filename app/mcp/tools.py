
"""
Smart-MCP Tool Registry  (v2)
==============================

Central state holder and tool-function library for the MCP server.

State registered at startup:
  _RETRIEVER   — HybridRetriever (search + graph)
  _ROUTES      — list[dict] from RouteMapper
  _INDEX_META  — repo metadata
  _MULTI_REPO  — MultiRepoManager (optional)
  _SERIALIZERS — list[dict] from SerializerLinker (optional)

All 15 MCP tools are implemented here as plain async functions.
server.py wraps them with @mcp.tool() decorators.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Shared state ────────────────────────────────────────────────────────── #

_RETRIEVER   = None   # HybridRetriever
_ROUTES:     list     = []
_INDEX_META: dict     = {}
_MULTI_REPO  = None   # MultiRepoManager | None
_SERIALIZERS: list    = []


def register_index(retriever, routes: list, meta: dict) -> None:
    """Called once by SmartMCP.build_index() after everything is ready."""
    global _RETRIEVER, _ROUTES, _INDEX_META
    _RETRIEVER  = retriever
    _ROUTES     = routes or []
    _INDEX_META = meta or {}

    # ── Lazy enrichment: serializer linking (Django repos) ────────── #
    global _SERIALIZERS
    if meta.get("framework") in ("django", "python") and meta.get("repo_path"):
        try:
            from app.core.serializer_linker import SerializerLinker
            linker = SerializerLinker(meta["repo_path"])
            _SERIALIZERS = linker.extract()
            logger.info(f"Serializer linker: {len(_SERIALIZERS)} serializers indexed")
        except Exception as exc:
            logger.debug(f"Serializer linker skipped: {exc}")

    logger.info(
        f"Index registered: {meta.get('chunk_count', '?')} chunks, "
        f"{len(_ROUTES)} routes, framework={meta.get('framework', '?')}"
    )


def register_multi_repo(manager) -> None:
    """Register a MultiRepoManager instance."""
    global _MULTI_REPO
    _MULTI_REPO = manager


# Backward-compat alias
def register_retriever(retriever) -> None:
    register_index(retriever, [], {})


# ── 1. search_context ───────────────────────────────────────────────────── #

async def tool_search_context(
    query: str,
    top_k: int = 8,
    file_filter: str = "",
    symbol_type: str = "",
) -> dict:
    """
    Hybrid semantic + keyword search. Primary retrieval tool.
    Returns results with file, line, type, decorators, docstring, source code.
    """
    if _RETRIEVER is None:
        return _not_indexed()
    results = _RETRIEVER.search(
        query=query, top_k=top_k,
        file_filter=file_filter, symbol_type=symbol_type,
    )
    return {"query": query, "count": len(results), "results": results}


# ── 2. search_with_budget ───────────────────────────────────────────────── #

async def tool_search_with_budget(
    query: str,
    max_tokens: int = 3000,
    file_filter: str = "",
    symbol_type: str = "",
) -> dict:
    """
    Token-budget-aware search. Returns as many relevant results as fit inside
    max_tokens. Perfect for controlling context window usage precisely.
    """
    if _RETRIEVER is None:
        return _not_indexed()

    from app.core.token_counter import TokenCounter

    # Fetch generously, then trim to budget
    candidates = _RETRIEVER.search(
        query=query, top_k=30,
        file_filter=file_filter, symbol_type=symbol_type,
    )
    selected, used = TokenCounter.fit_to_budget(candidates, max_tokens)
    return {
        "query":       query,
        "max_tokens":  max_tokens,
        "used_tokens": used,
        "budget_pct":  f"{round(used/max_tokens*100)}%" if max_tokens else "n/a",
        "count":       len(selected),
        "results":     selected,
    }


# ── 3. search_signatures ────────────────────────────────────────────────── #

async def tool_search_signatures(
    query: str,
    top_k: int = 20,
    file_filter: str = "",
) -> dict:
    """
    Returns only function/method signatures — no body code.
    Ultra-low token cost (~10–30 tokens per result vs 200–500 for full code).
    Use this first to discover WHAT exists, then call get_symbol for details.
    """
    if _RETRIEVER is None:
        return _not_indexed()

    from app.core.token_counter import TokenCounter

    results = _RETRIEVER.search(
        query=query, top_k=top_k, file_filter=file_filter,
    )
    signatures = TokenCounter.signatures_only(results)
    used = TokenCounter.count_results(signatures)
    return {
        "query":       query,
        "count":       len(signatures),
        "tokens_used": used,
        "note":        "Signatures only. Use get_symbol(name) for full code.",
        "results":     signatures,
    }


# ── 4. list_symbols ─────────────────────────────────────────────────────── #

async def tool_list_symbols(
    file_pattern: str = "",
    symbol_type: str = "",
    limit: int = 50,
) -> dict:
    """Browse the index without a query — list all indexed symbols."""
    if _RETRIEVER is None:
        return _not_indexed()
    symbols = _RETRIEVER.list_symbols(
        file_pattern=file_pattern, symbol_type=symbol_type, limit=limit,
    )
    return {"count": len(symbols), "symbols": symbols}


# ── 5. get_symbol ────────────────────────────────────────────────────────── #

async def tool_get_symbol(name: str, file: str = "") -> dict:
    """Exact-match lookup by symbol name. Returns full source code."""
    if _RETRIEVER is None:
        return _not_indexed()
    for doc in _RETRIEVER.documents:
        if doc.get("symbol", "").lower() == name.lower():
            if not file or file.lower() in doc.get("file", "").lower():
                return {"found": True, "result": _RETRIEVER._format_result(doc)}
    results = _RETRIEVER.search(query=name, top_k=3, file_filter=file)
    if results:
        return {
            "found": False,
            "note":  f"Exact match not found; returning closest matches.",
            "result": results[0],
            "also":   results[1:],
        }
    return {"found": False, "result": None}


# ── 6. find_usages ───────────────────────────────────────────────────────── #

async def tool_find_usages(symbol_name: str, top_k: int = 8) -> dict:
    """Find where a symbol is referenced — not where it's defined."""
    if _RETRIEVER is None:
        return _not_indexed()
    usages = _RETRIEVER.find_usages(symbol_name, top_k=top_k)
    return {"symbol": symbol_name, "count": len(usages), "usages": usages}


# ── 7. get_related ───────────────────────────────────────────────────────── #

async def tool_get_related(
    symbol_name: str,
    depth: int = 1,
    include_code: bool = True,
) -> dict:
    """
    Graph traversal: return all symbols related to symbol_name within
    *depth* hops (callers + callees + inherited classes).
    Depth 1 = direct neighbours only. Depth 2 = also their neighbours.
    Essential for understanding ripple effects of a change.
    """
    if _RETRIEVER is None:
        return _not_indexed()
    related = _RETRIEVER.get_related(symbol_name, depth=depth)
    if not include_code:
        from app.core.token_counter import TokenCounter
        related = TokenCounter.signatures_only(related)
    return {
        "symbol": symbol_name,
        "depth":  depth,
        "count":  len(related),
        "related": related,
    }


# ── 8. get_call_chain ────────────────────────────────────────────────────── #

async def tool_get_call_chain(
    symbol_name: str,
    depth: int = 3,
    direction: str = "down",
) -> dict:
    """
    Follow the call chain from a symbol.
    direction='down' → functions called by symbol_name (dependency chain).
    direction='up'   → functions that call symbol_name (impact chain).
    Use this to trace execution paths and understand data flow.
    """
    if _RETRIEVER is None:
        return _not_indexed()
    chain = _RETRIEVER.get_call_chain(symbol_name, depth=depth, direction=direction)
    return {
        "symbol":    symbol_name,
        "direction": direction,
        "depth":     depth,
        "count":     len(chain),
        "chain":     chain,
    }


# ── 9. explain_symbol ────────────────────────────────────────────────────── #

async def tool_explain_symbol(name: str, file: str = "") -> dict:
    """
    Full context for a symbol in one call:
      - definition (source code)
      - direct callers (what calls this)
      - direct callees (what this calls)
      - related by inheritance
    Use this instead of making 3–4 separate calls.
    """
    if _RETRIEVER is None:
        return _not_indexed()

    # Definition
    definition = None
    for doc in _RETRIEVER.documents:
        if doc.get("symbol", "").lower() == name.lower():
            if not file or file.lower() in doc.get("file", "").lower():
                definition = _RETRIEVER._format_result(doc)
                break

    if definition is None:
        results = _RETRIEVER.search(query=name, top_k=1, file_filter=file)
        definition = results[0] if results else None

    callers = _RETRIEVER.get_callers(name)
    callees = _RETRIEVER.get_callees(name)

    return {
        "symbol":     name,
        "definition": definition,
        "callers":    callers[:5],
        "callees":    callees[:5],
        "note": (
            "definition = the symbol's source code. "
            "callers = functions that call this. "
            "callees = functions this calls."
        ),
    }


# ── 10. search_by_file ──────────────────────────────────────────────────── #

async def tool_search_by_file(
    file_path: str,
    query: str = "",
    limit: int = 30,
) -> dict:
    """List or search symbols within a specific file."""
    if _RETRIEVER is None:
        return _not_indexed()
    if query:
        results = _RETRIEVER.search(query=query, top_k=limit, file_filter=file_path)
    else:
        results = _RETRIEVER.list_symbols(file_pattern=file_path, limit=limit)
    return {"file_filter": file_path, "query": query, "count": len(results), "results": results}


# ── 11. list_routes ──────────────────────────────────────────────────────── #

async def tool_list_routes(method: str = "", path_filter: str = "") -> dict:
    """List URL routes mapped to handler functions/views."""
    if not _ROUTES and _RETRIEVER is None:
        return _not_indexed()
    routes = _ROUTES
    if method:
        routes = [r for r in routes if method.upper() in r.get("method", "").upper()]
    if path_filter:
        pf = path_filter.lower()
        routes = [r for r in routes if pf in r.get("path", "").lower()]
    return {"count": len(routes), "routes": routes}


# ── 12. list_serializers ─────────────────────────────────────────────────── #

async def tool_list_serializers(model_filter: str = "") -> dict:
    """
    List all Django REST Framework serializers and their linked models.
    Answers: 'Which serializer handles the User model?' instantly.
    """
    if _RETRIEVER is None:
        return _not_indexed()
    serializers = _SERIALIZERS
    if model_filter:
        mf = model_filter.lower()
        serializers = [s for s in serializers
                       if mf in (s.get("model") or "").lower()
                       or mf in s.get("serializer", "").lower()]
    return {
        "count":       len(serializers),
        "serializers": serializers,
    }


# ── 13. get_repo_summary ─────────────────────────────────────────────────── #

async def tool_get_repo_summary() -> dict:
    """
    High-level codebase overview: frameworks, languages, top files, models,
    routes, hot symbols, dead code estimate — all in ~300–600 tokens.
    Use this FIRST when starting work on an unfamiliar repository.
    """
    if _RETRIEVER is None:
        return _not_indexed()
    from app.core.repo_summarizer import RepoSummarizer
    summarizer = RepoSummarizer(_RETRIEVER, _ROUTES, _INDEX_META)
    return summarizer.summarize()


# ── 14. find_dead_code ───────────────────────────────────────────────────── #

async def tool_find_dead_code(limit: int = 20) -> dict:
    """
    Find symbols that are defined but never called/referenced anywhere in
    the indexed codebase. Useful for cleanup and understanding code debt.
    Note: external callers (HTTP, tests, scripts) won't be visible here.
    """
    if _RETRIEVER is None:
        return _not_indexed()
    dead = _RETRIEVER.find_dead_code(limit=limit)
    return {
        "count":   len(dead),
        "note":    "These symbols have no internal callers in the indexed codebase.",
        "symbols": dead,
    }


# ── 15. get_index_stats ─────────────────────────────────────────────────── #

async def tool_get_index_stats() -> dict:
    """Index health: chunks, files, symbol types, framework, model, routes."""
    if _RETRIEVER is None:
        return _not_indexed()
    stats = _RETRIEVER.stats()
    stats["routes_indexed"] = len(_ROUTES)
    stats["repo_path"]      = _INDEX_META.get("repo_path", "unknown")
    stats["framework"]      = _INDEX_META.get("framework", "unknown")
    stats["indexed_at"]     = _INDEX_META.get("indexed_at", "unknown")
    if _MULTI_REPO:
        stats["multi_repo"] = [r["name"] for r in _MULTI_REPO.list_repos()]
    return stats


# ── Multi-repo helpers ───────────────────────────────────────────────────── #

async def tool_list_repos() -> dict:
    """List all indexed repositories in multi-repo mode."""
    if _MULTI_REPO is None or len(_MULTI_REPO) == 0:
        if _RETRIEVER is not None:
            return {
                "mode":  "single-repo",
                "repos": [{
                    "name":    "default",
                    "path":    _INDEX_META.get("repo_path", ""),
                    "framework": _INDEX_META.get("framework", ""),
                    "chunk_count": _INDEX_META.get("chunk_count", 0),
                }]
            }
        return _not_indexed()
    return {"mode": "multi-repo", "repos": _MULTI_REPO.list_repos()}


async def tool_search_all_repos(query: str, top_k: int = 8) -> dict:
    """Search across ALL indexed repositories. Returns merged ranked results."""
    if _MULTI_REPO is None:
        return await tool_search_context(query, top_k=top_k)
    results = _MULTI_REPO.search_all(query=query, top_k=top_k)
    return {"query": query, "count": len(results), "results": results}


# ── Backward-compat ──────────────────────────────────────────────────────── #

async def semantic_lookup(query: str) -> dict:
    return await tool_search_context(query)


# ── Internal helpers ─────────────────────────────────────────────────────── #

def _not_indexed() -> dict:
    return {
        "error": (
            "Repository not yet indexed. Smart-MCP is still building the "
            "index or no repository path was detected. Please wait a moment "
            "and retry, or check the server logs for errors."
        )
    }
