
"""
Smart-MCP Server  (v2)
======================

Exposes 15 MCP tools to any compatible AI agent:

  SEARCH  (token-aware)
    1.  search_context         — hybrid BM25 + FAISS, primary retrieval
    2.  search_with_budget     — stay within a token limit
    3.  search_signatures      — signatures only (~10–30 tok/result)
    4.  search_by_file         — scoped to a specific file

  SYMBOL LOOKUP
    5.  get_symbol             — exact lookup with full source code
    6.  find_usages            — where a symbol is called/imported
    7.  explain_symbol         — definition + callers + callees in one shot

  GRAPH TRAVERSAL
    8.  get_related            — BFS expansion (callers + callees + inherit)
    9.  get_call_chain         — follow call chain N levels deep

  NAVIGATION
    10. list_symbols           — browse index (no query needed)
    11. list_routes            — URL routes → handler mapping
    12. list_serializers       — Django serializer → model mapping

  ANALYSIS
    13. get_repo_summary       — full codebase overview in ~400 tokens
    14. find_dead_code         — symbols never called internally
    15. get_index_stats        — index health + statistics

All stdout is reserved for MCP JSON-RPC.  Logging goes to stderr.
"""

import sys
import os
import logging

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[smart-mcp] %(levelname)s: %(message)s",
)

_SMART_MCP_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _SMART_MCP_ROOT not in sys.path:
    sys.path.insert(0, _SMART_MCP_ROOT)

from mcp.server.fastmcp import FastMCP
from app.mcp.tools import (
    tool_search_context,
    tool_search_with_budget,
    tool_search_signatures,
    tool_list_symbols,
    tool_get_symbol,
    tool_find_usages,
    tool_get_related,
    tool_get_call_chain,
    tool_explain_symbol,
    tool_search_by_file,
    tool_list_routes,
    tool_list_serializers,
    tool_get_repo_summary,
    tool_find_dead_code,
    tool_get_index_stats,
    tool_list_repos,
    tool_search_all_repos,
)

mcp = FastMCP("smart-mcp")

# ── SEARCH tools ────────────────────────────────────────────────────────── #

@mcp.tool()
async def search_context(
    query: str,
    top_k: int = 8,
    file_filter: str = "",
    symbol_type: str = "",
):
    """
    Hybrid semantic + keyword search over the indexed repository.

    Returns the most relevant functions, classes, and methods for `query`,
    each with file path, line numbers, type, decorators, docstring, and
    actual source code.

    Args:
        query:       Natural-language or symbol/keyword query.
        top_k:       Max results (default 8).
        file_filter: Narrow to files whose path contains this string (e.g. "views.py").
        symbol_type: Narrow by type: function | class | method | route | …
    """
    return await tool_search_context(
        query=query, top_k=top_k,
        file_filter=file_filter, symbol_type=symbol_type,
    )


@mcp.tool()
async def search_with_budget(
    query: str,
    max_tokens: int = 3000,
    file_filter: str = "",
    symbol_type: str = "",
):
    """
    Token-budget-aware search: returns as many relevant results as fit
    inside `max_tokens`.

    Use this to precisely control how much context you consume. The response
    includes `used_tokens` and `budget_pct` so you always know your spend.

    Args:
        query:      The search query.
        max_tokens: Maximum tokens to return (default 3000).
        file_filter: Optional file path filter.
        symbol_type: Optional type filter.
    """
    return await tool_search_with_budget(
        query=query, max_tokens=max_tokens,
        file_filter=file_filter, symbol_type=symbol_type,
    )


@mcp.tool()
async def search_signatures(query: str, top_k: int = 20, file_filter: str = ""):
    """
    Return only function/method signatures — no body code.

    Ultra-low token cost: ~10–30 tokens per result vs 200–500 for full code.

    Use this to quickly scan what exists in a codebase, then call
    `get_symbol(name)` for the full implementation of what you need.

    Args:
        query:       Search query.
        top_k:       Max signatures to return (default 20).
        file_filter: Optional file path filter.
    """
    return await tool_search_signatures(
        query=query, top_k=top_k, file_filter=file_filter,
    )


@mcp.tool()
async def search_by_file(file_path: str, query: str = "", limit: int = 30):
    """
    List or search symbols within a specific file.

    `file_path` can be a partial path (e.g. "views.py" or "auth/serializers").
    If `query` is provided, results are ranked by relevance.

    Args:
        file_path: Partial or full file path.
        query:     Optional search query to rank results.
        limit:     Max results (default 30).
    """
    return await tool_search_by_file(file_path=file_path, query=query, limit=limit)


# ── SYMBOL LOOKUP tools ──────────────────────────────────────────────────── #

@mcp.tool()
async def get_symbol(name: str, file: str = ""):
    """
    Exact-match lookup for a symbol by name. Returns full source code.

    Args:
        name: Symbol name (function, class, method …).
        file: Optional partial file path to disambiguate.
    """
    return await tool_get_symbol(name=name, file=file)


@mcp.tool()
async def find_usages(symbol_name: str, top_k: int = 8):
    """
    Find places where `symbol_name` is *referenced* — not where it is defined.

    Useful for impact analysis, refactoring, and understanding call chains.

    Args:
        symbol_name: The symbol to find usages for.
        top_k:       Max results (default 8).
    """
    return await tool_find_usages(symbol_name=symbol_name, top_k=top_k)


@mcp.tool()
async def explain_symbol(name: str, file: str = ""):
    """
    Full context for a symbol in ONE call:
      • definition (source code)
      • direct callers (who calls this)
      • direct callees (what this calls)

    Use instead of making 3–4 separate calls. Saves 60–70% of tokens compared
    to manually chaining search_context + find_usages + get_related.

    Args:
        name: Symbol name.
        file: Optional partial file path to disambiguate.
    """
    return await tool_explain_symbol(name=name, file=file)


# ── GRAPH TRAVERSAL tools ────────────────────────────────────────────────── #

@mcp.tool()
async def get_related(symbol_name: str, depth: int = 1, include_code: bool = True):
    """
    Graph traversal: return all symbols related to `symbol_name` within
    `depth` BFS hops (callers + callees + inheritance).

    depth=1 → direct neighbours only (recommended starting point).
    depth=2 → also includes neighbours' neighbours.

    Args:
        symbol_name:  The symbol to explore.
        depth:        BFS depth (1 or 2 recommended; default 1).
        include_code: If False, returns signatures only (lower token cost).
    """
    return await tool_get_related(
        symbol_name=symbol_name, depth=depth, include_code=include_code,
    )


@mcp.tool()
async def get_call_chain(symbol_name: str, depth: int = 3, direction: str = "down"):
    """
    Follow the call chain from a symbol.

    direction='down' → functions called by symbol_name (what it depends on).
    direction='up'   → functions that call symbol_name (what depends on it).

    Args:
        symbol_name: Starting symbol.
        depth:       How many levels to traverse (default 3).
        direction:   'down' (dependencies) or 'up' (dependants).
    """
    return await tool_get_call_chain(
        symbol_name=symbol_name, depth=depth, direction=direction,
    )


# ── NAVIGATION tools ─────────────────────────────────────────────────────── #

@mcp.tool()
async def list_symbols(
    file_pattern: str = "",
    symbol_type: str = "",
    limit: int = 50,
):
    """
    Browse all indexed symbols without a query.

    Useful for exploring what has been parsed — e.g. all classes in a module,
    all Django views, all TypeScript interfaces.

    Args:
        file_pattern: Filter to files matching this pattern.
        symbol_type:  Filter by type (function, class, method, route, …).
        limit:        Max symbols to return (default 50).
    """
    return await tool_list_symbols(
        file_pattern=file_pattern, symbol_type=symbol_type, limit=limit,
    )


@mcp.tool()
async def list_routes(method: str = "", path_filter: str = ""):
    """
    List all URL routes in the repository mapped to their handler functions.

    Works for Django, FastAPI, Flask, Express.js, and Next.js file-system routing.

    Args:
        method:      Filter by HTTP method (GET, POST, PUT, DELETE …).
        path_filter: Filter routes whose path contains this string.
    """
    return await tool_list_routes(method=method, path_filter=path_filter)


@mcp.tool()
async def list_serializers(model_filter: str = ""):
    """
    List all Django REST Framework serializers and the models they represent.

    Instantly answers: 'Which serializer handles the User model?'

    Args:
        model_filter: Filter by model or serializer name (case-insensitive).
    """
    return await tool_list_serializers(model_filter=model_filter)


# ── ANALYSIS tools ────────────────────────────────────────────────────────── #

@mcp.tool()
async def get_repo_summary():
    """
    High-level codebase overview in ~300–600 tokens.

    Returns: framework, languages, file counts, models, routes summary,
    hot symbols (most-called), dead code estimate, index health.

    Use this FIRST when starting work on an unfamiliar repository — it gives
    the AI agent the 'lay of the land' without loading any source files.
    """
    return await tool_get_repo_summary()


@mcp.tool()
async def find_dead_code(limit: int = 20):
    """
    Find symbols that are defined but never called anywhere in the indexed
    codebase. Useful for identifying dead code and cleanup opportunities.

    Note: external callers (HTTP requests, test runners, CLI scripts) are
    not visible to the graph, so some results may be false positives.

    Args:
        limit: Max symbols to return (default 20).
    """
    return await tool_find_dead_code(limit=limit)


@mcp.tool()
async def get_index_stats():
    """
    Return statistics about the current index:
      - total chunks, unique files
      - symbol type distribution
      - detected framework and language
      - embedding model
      - number of routes indexed
      - graph edges (call relationships)
      - repository path and index timestamp
    """
    return await tool_get_index_stats()


# ── MULTI-REPO tools ──────────────────────────────────────────────────────── #

@mcp.tool()
async def list_repos():
    """
    List all indexed repositories.

    In single-repo mode, shows the one active repo.
    In multi-repo mode, shows all repos with their chunk counts, frameworks,
    and last-indexed timestamps.
    """
    return await tool_list_repos()


@mcp.tool()
async def search_all_repos(query: str, top_k: int = 8):
    """
    Search across ALL indexed repositories simultaneously.

    Results from different repos are merged with Reciprocal Rank Fusion
    and each result is tagged with its source repo name.

    Args:
        query:  The search query.
        top_k:  Total results across all repos (default 8).
    """
    return await tool_search_all_repos(query=query, top_k=top_k)


# ── Startup: auto-detect + build index ──────────────────────────────────── #

_CLIENT_ENV_VARS = [
    "CLAUDE_PROJECT_DIR", "CLAUDE_WORKSPACE",
    "VSCODE_WORKSPACE_FOLDER", "WORKSPACE_FOLDER",
    "CODEX_PROJECT_DIR", "CODEX_WORKSPACE",
    "PROJECT_ROOT", "MCP_PROJECT_ROOT", "MCP_WORKSPACE",
]


def _is_valid_project_dir(path: str) -> bool:
    if not path or not os.path.isdir(path):
        return False
    return os.path.normcase(os.path.abspath(path)) != os.path.normcase(_SMART_MCP_ROOT)


def _resolve_repo_path() -> str | None:
    positional = [a for a in sys.argv[1:] if not a.startswith("-")]
    if positional:
        path = os.path.abspath(positional[0])
        if _is_valid_project_dir(path):
            logging.info(f"Repo path from CLI argument: {path}")
            return path

    for var in _CLIENT_ENV_VARS:
        val = os.environ.get(var, "").strip()
        if val and _is_valid_project_dir(val):
            logging.info(f"Repo path from env var {var}: {val}")
            return os.path.abspath(val)

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_SMART_MCP_ROOT, ".env"))
    except ImportError:
        pass

    repo_env = os.environ.get("REPO_PATH", "").strip()
    if repo_env and _is_valid_project_dir(repo_env):
        logging.info(f"Repo path from REPO_PATH env var: {repo_env}")
        return os.path.abspath(repo_env)

    cwd = os.getcwd()
    if _is_valid_project_dir(cwd):
        logging.info(f"Repo path auto-detected from working directory: {cwd}")
        return cwd

    logging.warning(
        "Could not detect a project directory.\n"
        "  Options:\n"
        "    a) CLI arg:   python -m app.mcp.server <path>\n"
        "    b) Env var:   REPO_PATH=<path>  (in smart-mcp/.env)\n"
        "    c) Launch from inside the project folder."
    )
    return None


def _auto_build_index() -> None:
    force = "--force" in sys.argv or "-f" in sys.argv
    repo_path = _resolve_repo_path()
    if not repo_path:
        return
    logging.info(f"Building index for: {repo_path}")
    from app.main import SmartMCP as SmartMCPApp
    SmartMCPApp(repo_path, force_reindex=force).build_index()
    logging.info("Index ready — MCP server accepting queries.")


if __name__ == "__main__":
    _auto_build_index()
    mcp.run()
