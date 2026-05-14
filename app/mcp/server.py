
import sys
import os
import logging

# Route all log output to stderr — stdout is reserved for MCP JSON-RPC messages.
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="[smart-mcp] %(levelname)s: %(message)s")

# ---------------------------------------------------------------------------
# Importability: add the smart-mcp package root to sys.path based on the
# location of THIS file — not cwd — so the server works no matter which
# directory the MCP host (Claude Code, Codex, Cursor …) launched it from.
# ---------------------------------------------------------------------------
_SMART_MCP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _SMART_MCP_ROOT not in sys.path:
    sys.path.insert(0, _SMART_MCP_ROOT)

from mcp.server.fastmcp import FastMCP
from app.mcp.tools import semantic_lookup

mcp = FastMCP("smart-mcp")


@mcp.tool()
async def search_context(query: str):
    return await semantic_lookup(query)


# ---------------------------------------------------------------------------
# Env-vars that common MCP clients inject to signal the project/workspace root
# ---------------------------------------------------------------------------
_CLIENT_ENV_VARS = [
    # Claude Code (claude CLI)
    "CLAUDE_PROJECT_DIR",
    "CLAUDE_WORKSPACE",
    # VS Code / Cursor extension hosts
    "VSCODE_WORKSPACE_FOLDER",
    "WORKSPACE_FOLDER",
    # Codex / OpenAI tooling
    "CODEX_PROJECT_DIR",
    "CODEX_WORKSPACE",
    # Generic fallbacks used by some hosts
    "PROJECT_ROOT",
    "MCP_PROJECT_ROOT",
    "MCP_WORKSPACE",
]


def _is_valid_project_dir(path: str) -> bool:
    """Return True if path is a real directory that is not the smart-mcp package."""
    if not path or not os.path.isdir(path):
        return False
    return os.path.normcase(os.path.abspath(path)) != os.path.normcase(_SMART_MCP_ROOT)


def _resolve_repo_path() -> str | None:
    """
    Detect the project folder to index.  Resolution order (first match wins):

    1. CLI argument        — python -m app.mcp.server <path>
    2. Client env vars     — env vars injected by Claude Code / Codex / Cursor / …
    3. REPO_PATH env var   — set in smart-mcp's .env or in the system environment
    4. Working directory   — os.getcwd() at server startup
                             (= the folder the MCP host was launched from,
                              as long as no explicit cwd was set in the MCP config)

    Returns the resolved absolute path, or None if nothing usable was found.
    """

    # 1. CLI argument (first positional arg, ignoring flags)
    positional = [a for a in sys.argv[1:] if not a.startswith("-")]
    if positional:
        path = os.path.abspath(positional[0])
        if _is_valid_project_dir(path):
            logging.info(f"Repo path from CLI argument: {path}")
            return path
        logging.warning(f"CLI arg '{positional[0]}' is not a valid project directory — skipping.")

    # 2. Env vars injected by the MCP client
    for var in _CLIENT_ENV_VARS:
        val = os.environ.get(var, "").strip()
        if val and _is_valid_project_dir(val):
            logging.info(f"Repo path from env var {var}: {val}")
            return os.path.abspath(val)

    # 3. REPO_PATH from smart-mcp's own .env (explicit override)
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_SMART_MCP_ROOT, ".env"))
    except ImportError:
        pass

    repo_env = os.environ.get("REPO_PATH", "").strip()
    if repo_env and _is_valid_project_dir(repo_env):
        logging.info(f"Repo path from REPO_PATH env var: {repo_env}")
        return os.path.abspath(repo_env)

    # 4. Working directory — inherited from the MCP host process
    cwd = os.getcwd()
    if _is_valid_project_dir(cwd):
        logging.info(f"Repo path auto-detected from working directory: {cwd}")
        return cwd

    logging.warning(
        "Could not detect a project directory.\n"
        "  Options:\n"
        "    a) Pass path as CLI arg:  python -m app.mcp.server <path>\n"
        "    b) Set env var:           REPO_PATH=<path>  (in smart-mcp/.env)\n"
        "    c) Launch the MCP host from inside the project folder."
    )
    return None


def _auto_build_index():
    repo_path = _resolve_repo_path()
    if not repo_path:
        return

    logging.info(f"Building index for: {repo_path}")
    from app.main import SmartMCP as SmartMCPApp
    SmartMCPApp(repo_path).build_index()
    logging.info("Index ready.")


if __name__ == "__main__":
    _auto_build_index()
    mcp.run()
