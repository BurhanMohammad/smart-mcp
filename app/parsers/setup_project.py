"""
setup_project.py
================

One-command setup for a single project.

What it does:
  1. Writes  <project>/.claude/mcp.json   — wires smart-mcp as an MCP server
                                            for Claude Code launched in this project
  2. Writes  <project>/CLAUDE.md           — instructs Claude to use smart-mcp
                                            automatically (no tool names needed)
  3. Optionally pre-builds the index now   — so first query is instant

Usage:
  # From inside the project you want to set up:
  python C:\\Work\\smart-mcp\\setup_project.py

  # Or pass the project path explicitly:
  python C:\\Work\\smart-mcp\\setup_project.py C:\\Work\\MyProject

  # Skip the index pre-build (build happens automatically on first AI query):
  python C:\\Work\\smart-mcp\\setup_project.py --no-index

  # See what would be written without touching files:
  python C:\\Work\\smart-mcp\\setup_project.py --dry-run

After running this script:
  - Open the project in Claude Code (or Cursor, Codex …)
  - Just type naturally: "the login is not working"
  - Claude will automatically search the codebase and fix it
  - No tool names, no manual commands needed
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────── #

SMART_MCP_ROOT  = Path(__file__).resolve().parent
PYTHON_EXE      = sys.executable
CLAUDE_MD_TMPL  = SMART_MCP_ROOT / "app" / "templates" / "CLAUDE.md"


# ── CLI ──────────────────────────────────────────────────────────────────── #

def _parse_args():
    p = argparse.ArgumentParser(
        description="Set up Smart-MCP for a project (writes mcp.json + CLAUDE.md)."
    )
    p.add_argument(
        "project_path",
        nargs="?",
        default=None,
        help="Path to the project. Defaults to current directory.",
    )
    p.add_argument(
        "--no-index",
        action="store_true",
        help="Skip pre-building the index (it will be built on first AI query).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be written without touching any files.",
    )
    return p.parse_args()


# ── Helpers ──────────────────────────────────────────────────────────────── #

def _resolve_project(raw: str | None) -> Path:
    if raw:
        p = Path(raw).resolve()
        if not p.is_dir():
            _die(f"'{raw}' is not a valid directory.")
        return p
    return Path.cwd()


def _die(msg: str):
    print(f"\n[setup_project] ERROR: {msg}")
    sys.exit(1)


def _print_section(title: str):
    print(f"\n{'─' * 50}")
    print(f"  {title}")
    print(f"{'─' * 50}")


# ── 1. Write .claude/mcp.json ────────────────────────────────────────────── #

def _build_mcp_config(project_path: Path) -> dict:
    """
    The server receives the project path as a CLI argument (highest priority).
    cwd is set to SMART_MCP_ROOT so `app` is importable.
    """
    return {
        "mcpServers": {
            "smart-mcp": {
                "command": str(PYTHON_EXE),
                "args": [
                    "-m",
                    "app.mcp.server",
                    str(project_path),   # explicit path — survives any cwd change
                ],
                "cwd": str(SMART_MCP_ROOT),
                "env": {
                    "PYTHONPATH": str(SMART_MCP_ROOT),
                },
            }
        }
    }


def _write_mcp_json(project_path: Path, dry_run: bool):
    claude_dir  = project_path / ".claude"
    config_path = claude_dir / "mcp.json"
    config      = _build_mcp_config(project_path)

    if dry_run:
        print(f"\n[DRY RUN] Would write: {config_path}")
        print("  " + json.dumps(config, indent=2).replace("\n", "\n  "))
        return

    claude_dir.mkdir(parents=True, exist_ok=True)

    # Back up existing file if present
    if config_path.exists():
        bak = config_path.with_suffix(".json.bak")
        shutil.copy(config_path, bak)
        print(f"  Backed up existing mcp.json → {bak.name}")

    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"  ✓ Written: {config_path}")


# ── 2. Write CLAUDE.md ───────────────────────────────────────────────────── #

def _write_claude_md(project_path: Path, dry_run: bool):
    dest = project_path / "CLAUDE.md"

    if not CLAUDE_MD_TMPL.exists():
        print(f"  [warn] Template not found: {CLAUDE_MD_TMPL} — skipping CLAUDE.md")
        return

    template_text = CLAUDE_MD_TMPL.read_text(encoding="utf-8")

    if dry_run:
        print(f"\n[DRY RUN] Would write: {dest}")
        print(f"  ({len(template_text)} bytes)")
        return

    if dest.exists():
        bak = dest.with_suffix(".md.bak")
        shutil.copy(dest, bak)
        print(f"  Backed up existing CLAUDE.md → {bak.name}")

    dest.write_text(template_text, encoding="utf-8")
    print(f"  ✓ Written: {dest}")


# ── 3. Pre-build index ───────────────────────────────────────────────────── #

def _build_index(project_path: Path):
    print("\n  Building index (this may take a minute on first run) …")
    try:
        # Add smart-mcp root to path so we can import app
        if str(SMART_MCP_ROOT) not in sys.path:
            sys.path.insert(0, str(SMART_MCP_ROOT))

        from app.main import SmartMCP
        SmartMCP(str(project_path)).build_index()
        print("  ✓ Index built and cached — first query will be instant.")
    except Exception as exc:
        print(f"  [warn] Index build failed: {exc}")
        print("  Index will be built automatically when Claude Code starts.")


# ── Main ─────────────────────────────────────────────────────────────────── #

def run():
    args         = _parse_args()
    project_path = _resolve_project(args.project_path)

    # Sanity check: don't point at smart-mcp itself
    if project_path.resolve() == SMART_MCP_ROOT.resolve():
        _die(
            "The project path is the smart-mcp directory itself.\n"
            "  Pass the path of the project you want to index, not smart-mcp."
        )

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║        Smart-MCP  —  Project Setup               ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"\n  Project  : {project_path}")
    print(f"  Python   : {PYTHON_EXE}")
    print(f"  Mode     : {'DRY RUN' if args.dry_run else 'LIVE'}")

    # ── Write mcp.json ──
    _print_section("1 / 3  Writing .claude/mcp.json")
    _write_mcp_json(project_path, args.dry_run)

    # ── Write CLAUDE.md ──
    _print_section("2 / 3  Writing CLAUDE.md")
    _write_claude_md(project_path, args.dry_run)

    # ── Pre-build index ──
    _print_section("3 / 3  Pre-building index")
    if args.dry_run:
        print("  [DRY RUN] Would build index now.")
    elif args.no_index:
        print("  Skipped (--no-index). Index will be built on first AI query.")
    else:
        _build_index(project_path)

    # ── Summary ──
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║  Setup complete!                                  ║")
    print("╚══════════════════════════════════════════════════╝")
    print()
    print("  What was set up:")
    print(f"    {project_path / '.claude' / 'mcp.json'}")
    print(f"    {project_path / 'CLAUDE.md'}")
    print()
    print("  How to use:")
    print("    1. Open this project in Claude Code (or Cursor / Codex)")
    print("    2. Just type naturally — Smart-MCP works automatically")
    print()
    print("  Example prompts (no tool names needed):")
    print('    "the authentication is not working"')
    print('    "how does the payment flow work"')
    print('    "add a new endpoint for user profile update"')
    print('    "what endpoints do we have"')
    print('    "explain the order creation process"')
    print()
    print("  To re-index after code changes:")
    print(f"    python -m app.mcp.server {project_path} --force")
    print()


if __name__ == "__main__":
    run()
