"""
setup_global.py
===============
One-time global setup for smart-mcp.

Writes the smart-mcp MCP server entry into the config files of every
MCP-compatible client found on this machine (Claude Code, Codex, Cursor,
Windsurf, Continue …).

KEY DESIGN — zero-config auto-detection
-----------------------------------------
The generated configs intentionally do NOT set "cwd".  This means the MCP
server process inherits its working directory directly from the client that
launches it (Claude Code, Codex, etc.).  server.py then uses os.getcwd() as
the project path to index — so whichever folder you open in Claude Code /
Codex is the folder that gets indexed automatically.  No per-project setup,
no manual REPO_PATH.

Usage
-----
    python C:\\Work\\smart-mcp\\setup_global.py          # detect all clients
    python C:\\Work\\smart-mcp\\setup_global.py --dry-run # show what would change
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
SMART_MCP_ROOT = Path(__file__).resolve().parent
PYTHON_EXE = sys.executable

# The MCP server entry — NO "cwd" key so the host's working directory is inherited
MCP_SERVER_ENTRY = {
    "command": str(PYTHON_EXE),
    "args": ["-m", "app.mcp.server"],
    # "cwd" is intentionally absent — inherited from the MCP host process
    "env": {
        # Ensure `app` is importable regardless of the launch directory
        "PYTHONPATH": str(SMART_MCP_ROOT),
    },
}

# ---------------------------------------------------------------------------
# Client config locations
# Each entry: (client_label, config_path, config_key_path)
#   config_key_path — list of nested keys leading to the mcpServers dict
# ---------------------------------------------------------------------------
HOME = Path.home()
APPDATA = Path(os.environ.get("APPDATA", HOME / "AppData" / "Roaming"))

CLIENTS: list[tuple[str, Path, list[str]]] = [
    # Claude Code CLI  (~/.claude.json  or  ~/.claude/mcp.json depending on version)
    (
        "Claude Code (~/.claude/mcp.json)",
        HOME / ".claude" / "mcp.json",
        ["mcpServers"],
    ),
    (
        "Claude Code (~/.claude.json)",
        HOME / ".claude.json",
        ["mcpServers"],
    ),
    # Claude Desktop (Windows)
    (
        "Claude Desktop (claude_desktop_config.json)",
        APPDATA / "Claude" / "claude_desktop_config.json",
        ["mcpServers"],
    ),
    # Codex CLI
    (
        "Codex (~/.codex/config.json)",
        HOME / ".codex" / "config.json",
        ["mcpServers"],
    ),
    # Cursor
    (
        "Cursor (~/.cursor/mcp.json)",
        HOME / ".cursor" / "mcp.json",
        ["mcpServers"],
    ),
    # Windsurf
    (
        "Windsurf (~/.windsurf/mcp.json)",
        HOME / ".windsurf" / "mcp.json",
        ["mcpServers"],
    ),
    # Continue (VS Code extension)
    (
        "Continue (~/.continue/config.json)",
        HOME / ".continue" / "config.json",
        ["mcpServers"],
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"  [warn] {path} exists but is not valid JSON — will overwrite the mcpServers section only.")
    return {}


def _write_json(path: Path, data: dict, dry_run: bool):
    if dry_run:
        print(f"  [dry-run] Would write: {path}")
        print("  " + json.dumps(data, indent=2).replace("\n", "\n  "))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"  Written: {path}")


def _set_nested(d: dict, key_path: list[str], value: dict):
    """Ensure d[key_path[0]][key_path[1]]… exists and merge value into it."""
    for key in key_path[:-1]:
        d = d.setdefault(key, {})
    d.setdefault(key_path[-1], {})
    d[key_path[-1]]["smart-mcp"] = value


def _get_nested(d: dict, key_path: list[str]) -> dict:
    for key in key_path:
        d = d.get(key, {})
    return d


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run: bool = False):
    print(f"smart-mcp global setup")
    print(f"  smart-mcp root : {SMART_MCP_ROOT}")
    print(f"  Python         : {PYTHON_EXE}")
    print(f"  Mode           : {'DRY RUN (no files written)' if dry_run else 'LIVE'}")
    print()

    updated: list[str] = []
    skipped: list[str] = []

    for label, config_path, key_path in CLIENTS:
        # Only update configs for clients that already have a config file OR
        # whose config directory already exists (client is installed).
        if not config_path.exists() and not config_path.parent.exists():
            skipped.append(label)
            continue

        print(f"[{label}]")
        data = _read_json(config_path)

        existing = _get_nested(data, key_path).get("smart-mcp")
        if existing == MCP_SERVER_ENTRY:
            print(f"  Already up to date — no changes needed.")
            print()
            continue

        _set_nested(data, key_path, MCP_SERVER_ENTRY)
        _write_json(config_path, data, dry_run)
        updated.append(label)
        print()

    # Summary
    print("=" * 60)
    if updated:
        print(f"Updated {len(updated)} client(s):")
        for c in updated:
            print(f"  ✓ {c}")
    else:
        print("No clients needed updating.")

    if skipped:
        print(f"\nSkipped {len(skipped)} client(s) not installed on this machine:")
        for c in skipped:
            print(f"  – {c}")

    print()
    print("How auto-detection works after this setup")
    print("-" * 42)
    print("  • Open Claude Code / Codex / Cursor in any project folder.")
    print("  • smart-mcp starts automatically and indexes THAT folder.")
    print("  • No REPO_PATH, no per-project config files needed.")
    print()
    print("Priority order if you ever want to override:")
    print("  1. CLI arg  — python -m app.mcp.server <path>")
    print("  2. Env vars — CLAUDE_PROJECT_DIR / CODEX_PROJECT_DIR / PROJECT_ROOT / …")
    print("  3. REPO_PATH in smart-mcp/.env")
    print("  4. Auto-detected cwd  ← default for all zero-config setups")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Global smart-mcp MCP client setup")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without touching any files.",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)
