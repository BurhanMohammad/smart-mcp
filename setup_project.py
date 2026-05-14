"""
setup_project.py — Auto-generate .claude/mcp.json for any project so that
smart-mcp indexes THAT project whenever Claude is launched inside it.

Usage:
    # From inside the project you want to set up:
    python C:\\Work\\smart-mcp\\setup_project.py

    # Or pass the project path explicitly:
    python C:\\Work\\smart-mcp\\setup_project.py C:\\Work\\MyOtherProject
"""

import json
import os
import sys

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------

SMART_MCP_ROOT = os.path.dirname(os.path.abspath(__file__))

# Python interpreter used in this environment
PYTHON_EXE = sys.executable


def find_project_path():
    """Return the target project directory."""
    if len(sys.argv) > 1:
        candidate = os.path.abspath(sys.argv[1])
        if os.path.isdir(candidate):
            return candidate
        print(f"[setup_project] '{candidate}' is not a valid directory.")
        sys.exit(1)
    # Default: directory this script is called from
    return os.getcwd()


def build_mcp_config(project_path: str) -> dict:
    """
    Build the .claude/mcp.json content for the given project.

    The MCP server receives the project path as:
      - A CLI argument (highest priority in server.py)

    The server module lives in SMART_MCP_ROOT so we pass that as cwd so
    Python can resolve `app.mcp.server` correctly.
    """
    return {
        "mcpServers": {
            "smart-mcp": {
                "command": PYTHON_EXE,
                "args": [
                    "-m",
                    "app.mcp.server",
                    project_path          # <-- explicit repo path as CLI arg
                ],
                "cwd": SMART_MCP_ROOT    # <-- so `app` package is importable
            }
        }
    }


def write_mcp_config(project_path: str):
    claude_dir = os.path.join(project_path, ".claude")
    os.makedirs(claude_dir, exist_ok=True)

    config_path = os.path.join(claude_dir, "mcp.json")

    config = build_mcp_config(project_path)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"[setup_project] Written: {config_path}")
    print()
    print("  Project  :", project_path)
    print("  Python   :", PYTHON_EXE)
    print("  Server   :", os.path.join(SMART_MCP_ROOT, "app", "mcp", "server.py"))
    print()
    print("When Claude Code is launched inside this project, smart-mcp will")
    print("automatically index it — no manual REPO_PATH configuration needed.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    project_path = find_project_path()

    # Don't let the user accidentally point setup at smart-mcp itself
    if os.path.normcase(project_path) == os.path.normcase(SMART_MCP_ROOT):
        print("[setup_project] Warning: project path is the smart-mcp root itself.")
        print("  Pass the path to the project you want to index, not smart-mcp.")
        sys.exit(1)

    write_mcp_config(project_path)
