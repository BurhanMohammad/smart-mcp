"""
setup_global.py
===============

One-time machine-wide setup for Smart-MCP.

What it does:
  1. Registers smart-mcp in every AI client found on this machine
     (Claude Code, Claude Desktop, Cursor, Codex, Windsurf, Continue …)

  2. Writes ~/.claude/CLAUDE.md  — global instructions so Claude AUTOMATICALLY
     uses Smart-MCP tools whenever you just type naturally, across ALL projects.
     You never need to mention tool names.

  3. Warns about (and optionally clears) a hardcoded REPO_PATH in smart-mcp/.env
     which would override auto-detection and break multi-project use.

KEY DESIGN — zero-config per-project auto-detection
----------------------------------------------------
After this setup, Smart-MCP indexes whichever folder you open in Claude Code.
No REPO_PATH, no per-project mcp.json.

If you want project-specific setup (e.g. to pre-build the index):
  python setup_project.py <path>

Usage:
  python C:\\Work\\smart-mcp\\setup_global.py          # register all clients
  python C:\\Work\\smart-mcp\\setup_global.py --dry-run # show changes only
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────── #

SMART_MCP_ROOT = Path(__file__).resolve().parent
PYTHON_EXE     = sys.executable
HOME           = Path.home()
APPDATA        = Path(os.environ.get("APPDATA", HOME / "AppData" / "Roaming"))
CLAUDE_MD_TMPL = SMART_MCP_ROOT / "app" / "templates" / "CLAUDE.md"
ENV_FILE       = SMART_MCP_ROOT / ".env"

# ── MCP server entry (no cwd → inherits from AI client → auto-detects project) #

MCP_ENTRY = {
    "command": str(PYTHON_EXE),
    "args":    ["-m", "app.mcp.server"],
    # No "cwd" — the MCP host's working directory becomes the project path
    "env": {
        "PYTHONPATH": str(SMART_MCP_ROOT),
    },
}

# ── Known AI client config locations ─────────────────────────────────────── #
#   (label, config_path, key_path_to_mcpServers_dict)

CLIENTS: list[tuple[str, Path, list[str]]] = [
    # Claude Code CLI
    ("Claude Code  (~/.claude/mcp.json)",
     HOME / ".claude" / "mcp.json",           ["mcpServers"]),
    ("Claude Code  (~/.claude.json)",
     HOME / ".claude.json",                    ["mcpServers"]),
    # Claude Desktop (Windows)
    ("Claude Desktop  (claude_desktop_config.json)",
     APPDATA / "Claude" / "claude_desktop_config.json", ["mcpServers"]),
    # Claude Desktop (macOS)
    ("Claude Desktop  (macOS)",
     HOME / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
     ["mcpServers"]),
    # Cursor
    ("Cursor  (~/.cursor/mcp.json)",
     HOME / ".cursor" / "mcp.json",            ["mcpServers"]),
    # Codex CLI
    ("Codex  (~/.codex/config.json)",
     HOME / ".codex" / "config.json",          ["mcpServers"]),
    # Windsurf
    ("Windsurf  (~/.windsurf/mcp.json)",
     HOME / ".windsurf" / "mcp.json",          ["mcpServers"]),
    # Continue (VS Code extension)
    ("Continue  (~/.continue/config.json)",
     HOME / ".continue" / "config.json",       ["mcpServers"]),
]


# ── Helpers ──────────────────────────────────────────────────────────────── #

def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"    [warn] {path.name} exists but is invalid JSON — merging carefully.")
    return {}


def _write_json(path: Path, data: dict, dry_run: bool):
    if dry_run:
        print(f"    [DRY RUN] Would write: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"    ✓ Written: {path}")


def _set_mcp_entry(data: dict, key_path: list[str]):
    d = data
    for key in key_path[:-1]:
        d = d.setdefault(key, {})
    d.setdefault(key_path[-1], {})["smart-mcp"] = MCP_ENTRY


def _get_mcp_entry(data: dict, key_path: list[str]) -> dict | None:
    d = data
    for key in key_path:
        d = d.get(key, {})
    return d.get("smart-mcp")


def _print_section(title: str):
    print(f"\n{'─' * 56}")
    print(f"  {title}")
    print(f"{'─' * 56}")


# ── 1. Register MCP clients ──────────────────────────────────────────────── #

def _register_clients(dry_run: bool) -> tuple[list[str], list[str]]:
    updated: list[str] = []
    skipped: list[str] = []

    for label, config_path, key_path in CLIENTS:
        # Only touch if the client directory already exists (client is installed)
        if not config_path.exists() and not config_path.parent.exists():
            skipped.append(label)
            continue

        print(f"\n  [{label}]")
        data     = _read_json(config_path)
        existing = _get_mcp_entry(data, key_path)

        if existing == MCP_ENTRY:
            print("    Already up to date — no changes needed.")
            continue

        _set_mcp_entry(data, key_path)
        _write_json(config_path, data, dry_run)
        updated.append(label)

    return updated, skipped


# ── 2. Write global CLAUDE.md ────────────────────────────────────────────── #

def _write_global_claude_md(dry_run: bool):
    """
    Write ~/.claude/CLAUDE.md so Claude Code uses Smart-MCP automatically
    in every project on this machine — no per-project CLAUDE.md needed.
    """
    if not CLAUDE_MD_TMPL.exists():
        print(f"  [warn] Template not found: {CLAUDE_MD_TMPL} — skipping CLAUDE.md")
        return

    dest = HOME / ".claude" / "CLAUDE.md"
    text = CLAUDE_MD_TMPL.read_text(encoding="utf-8")

    if dry_run:
        print(f"\n  [DRY RUN] Would write: {dest}")
        print(f"  ({len(text)} bytes — Smart-MCP auto-dispatch instructions)")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)

    # If there's already a CLAUDE.md, append rather than overwrite
    if dest.exists():
        existing = dest.read_text(encoding="utf-8")
        if "Smart-MCP" in existing:
            # Already has our section — overwrite cleanly
            bak = dest.with_suffix(".md.bak")
            shutil.copy(dest, bak)
            print(f"  Backed up existing CLAUDE.md → {bak.name}")
            dest.write_text(text, encoding="utf-8")
        else:
            # Append our section after the existing content
            separator = "\n\n---\n\n"
            dest.write_text(existing + separator + text, encoding="utf-8")
            print(f"  Appended Smart-MCP section to existing CLAUDE.md")
    else:
        dest.write_text(text, encoding="utf-8")

    print(f"  ✓ Written: {dest}")


# ── 3. Check / fix .env ──────────────────────────────────────────────────── #

def _check_env(dry_run: bool):
    """
    Warn if REPO_PATH is hardcoded in .env (breaks multi-project auto-detection).
    Offer to comment it out.
    """
    if not ENV_FILE.exists():
        return

    lines    = ENV_FILE.read_text(encoding="utf-8").splitlines()
    problems = [
        i for i, ln in enumerate(lines)
        if ln.strip().startswith("REPO_PATH=") and not ln.strip().startswith("#")
    ]

    if not problems:
        print("  ✓ .env looks clean — no hardcoded REPO_PATH found.")
        return

    for i in problems:
        print(f"  [warn] .env line {i+1}: {lines[i].strip()}")
    print()
    print("  A hardcoded REPO_PATH overrides auto-detection and means smart-mcp")
    print("  will ALWAYS index that one project, even when you open a different one.")
    print()

    if dry_run:
        print("  [DRY RUN] Would comment out the REPO_PATH line(s).")
        return

    answer = input("  Comment out REPO_PATH now? [Y/n] ").strip().lower()
    if answer in ("", "y", "yes"):
        for i in problems:
            lines[i] = "# " + lines[i]
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("  ✓ REPO_PATH commented out — auto-detection is now active.")
    else:
        print("  Skipped. Multi-project auto-detection will not work until REPO_PATH is removed.")


# ── Main ─────────────────────────────────────────────────────────────────── #

def run(dry_run: bool = False):
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║       Smart-MCP  —  Global Machine Setup             ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"\n  smart-mcp root : {SMART_MCP_ROOT}")
    print(f"  Python         : {PYTHON_EXE}")
    print(f"  Mode           : {'DRY RUN (no files written)' if dry_run else 'LIVE'}")

    # ── 1. Register MCP clients ──
    _print_section("1 / 3  Registering AI clients")
    updated, skipped = _register_clients(dry_run)

    # ── 2. Write global CLAUDE.md ──
    _print_section("2 / 3  Writing global CLAUDE.md  (~/.claude/CLAUDE.md)")
    _write_global_claude_md(dry_run)

    # ── 3. Check .env ──
    _print_section("3 / 3  Checking .env for hardcoded REPO_PATH")
    _check_env(dry_run)

    # ── Summary ──
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Global setup complete!                               ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    if updated:
        print(f"  Updated {len(updated)} AI client(s):")
        for c in updated:
            print(f"    ✓ {c}")
    else:
        print("  No client configs needed updating.")

    if skipped:
        print(f"\n  Skipped {len(skipped)} client(s) (not installed on this machine):")
        for c in skipped:
            print(f"    – {c}")

    print()
    print("  How it works now — zero per-project setup:")
    print()
    print("    1.  Open ANY project folder in Claude Code (Cursor, Codex …)")
    print("    2.  Smart-MCP auto-starts and indexes THAT project")
    print("    3.  Just type naturally:")
    print()
    print('        "the login is not working"')
    print('        "how does the payment flow work"')
    print('        "add email notifications feature"')
    print('        "what API endpoints do we have"')
    print()
    print("    Claude reads CLAUDE.md and calls Smart-MCP tools automatically.")
    print("    You never need to mention tool names.")
    print()
    print("  Switching projects:")
    print("    Just open a different folder — Smart-MCP detects and indexes it.")
    print()
    print("  Want per-project setup (pre-build index, custom config)?")
    print(f"    python {SMART_MCP_ROOT / 'setup_project.py'} <project_path>")
    print()
    print("  Resolution order for repo path:")
    print("    1. CLI arg     python -m app.mcp.server <path>")
    print("    2. Client env  CLAUDE_PROJECT_DIR / VSCODE_WORKSPACE_FOLDER / …")
    print("    3. REPO_PATH   in smart-mcp/.env  (disabled if commented out)")
    print("    4. Auto-detect cwd  ← default after this setup")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Global smart-mcp setup for all AI clients.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be written without touching any files.",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)
