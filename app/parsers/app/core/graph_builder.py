
"""
GraphBuilder
============

Builds a caller→callee directed graph from the indexed chunks.

Works in two layers:
  1. Python (AST-precise): calls are extracted by python_parser.py and stored
     in chunk["calls"] as a list of function names called inside that body.
  2. Generic (regex-approximate): for TypeScript/Dart/Go chunks, we scan the
     code text for symbol-name appearances to infer likely calls.

The graph is stored as a `networkx.DiGraph` and exposed on `HybridRetriever`
so every graph-aware MCP tool can use it.

Graph edge types:
  "calls"   — function A calls function B
  "imports" — file A imports from file B  (future)
  "inherits" — class A extends class B
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Optional

import networkx as nx

logger = logging.getLogger(__name__)


class GraphBuilder:
    """
    Parameters
    ----------
    chunks : list[dict]
        The fully-built chunks from ASTChunker (after symbol IDs are assigned).
    """

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        # name → list of chunk ids (same name can appear in multiple files)
        self._name_to_ids: dict[str, list[str]] = defaultdict(list)
        # id → chunk
        self._id_to_chunk: dict[str, dict]      = {}

        for chunk in chunks:
            self._id_to_chunk[chunk["id"]] = chunk
            name = chunk.get("symbol", "")
            if name:
                self._name_to_ids[name].append(chunk["id"])

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def build(self) -> nx.DiGraph:
        """
        Build and return the full dependency graph.

        Nodes  : chunk IDs
        Edges  : directed, with relation type in edge data
        """
        G = nx.DiGraph()

        # Add all chunks as nodes with lightweight attributes
        for chunk in self.chunks:
            G.add_node(
                chunk["id"],
                symbol    = chunk.get("symbol", ""),
                type      = chunk.get("type", ""),
                file      = chunk.get("file", ""),
                class_name= chunk.get("class_name", ""),
            )

        # ── 1. Caller→Callee edges (from AST call extraction) ──────── #
        for chunk in self.chunks:
            calls = chunk.get("calls", [])
            if not calls:
                continue
            caller_id = chunk["id"]
            caller_file = chunk.get("file", "")

            for callee_name in calls:
                callee_ids = self._resolve(callee_name, caller_file)
                for callee_id in callee_ids:
                    if callee_id != caller_id:
                        G.add_edge(caller_id, callee_id, relation="calls")

        # ── 2. Inheritance edges ───────────────────────────────────── #
        for chunk in self.chunks:
            bases = chunk.get("base_classes", [])
            for base in bases:
                base_ids = self._resolve(base, chunk.get("file", ""))
                for base_id in base_ids:
                    G.add_edge(chunk["id"], base_id, relation="inherits")

        # ── 3. Generic code-scan edges (non-Python languages) ──────── #
        self._add_generic_edges(G)

        logger.info(
            f"GraphBuilder: {G.number_of_nodes()} nodes, "
            f"{G.number_of_edges()} edges"
        )
        return G

    def callers_of(self, symbol_name: str, G: nx.DiGraph) -> list[dict]:
        """Return chunks that CALL *symbol_name*."""
        target_ids = set(self._name_to_ids.get(symbol_name, []))
        results = []
        for src, tgt, data in G.edges(data=True):
            if tgt in target_ids and data.get("relation") == "calls":
                c = self._id_to_chunk.get(src)
                if c:
                    results.append(c)
        return results

    def callees_of(self, symbol_name: str, G: nx.DiGraph) -> list[dict]:
        """Return chunks CALLED BY *symbol_name*."""
        source_ids = set(self._name_to_ids.get(symbol_name, []))
        results = []
        for src in source_ids:
            for _, tgt, data in G.out_edges(src, data=True):
                if data.get("relation") == "calls":
                    c = self._id_to_chunk.get(tgt)
                    if c:
                        results.append(c)
        return results

    def related(
        self,
        symbol_name: str,
        G: nx.DiGraph,
        depth: int = 1,
    ) -> list[dict]:
        """
        BFS expansion: return all chunks reachable from *symbol_name* within
        *depth* hops (both incoming and outgoing edges).
        """
        start_ids = set(self._name_to_ids.get(symbol_name, []))
        if not start_ids:
            return []

        visited: set[str] = set(start_ids)
        frontier: set[str] = set(start_ids)

        for _ in range(depth):
            next_frontier: set[str] = set()
            for node_id in frontier:
                # outgoing (callees, inherited-by)
                for _, tgt in G.out_edges(node_id):
                    if tgt not in visited:
                        next_frontier.add(tgt)
                # incoming (callers)
                for src, _ in G.in_edges(node_id):
                    if src not in visited:
                        next_frontier.add(src)
            visited |= next_frontier
            frontier = next_frontier

        # Exclude the original symbol itself
        result_ids = visited - start_ids
        return [self._id_to_chunk[i] for i in result_ids if i in self._id_to_chunk]

    def call_chain(
        self,
        symbol_name: str,
        G: nx.DiGraph,
        depth: int = 3,
        direction: str = "down",
    ) -> list[dict]:
        """
        Follow the call chain from *symbol_name*.

        direction="down"  → functions called by symbol_name (and their callees)
        direction="up"    → functions that call symbol_name (and their callers)
        """
        start_ids = self._name_to_ids.get(symbol_name, [])
        if not start_ids:
            return []

        visited: set[str] = set()
        result_ids: list[str] = []

        def _dfs(node_id: str, remaining: int) -> None:
            if remaining <= 0 or node_id in visited:
                return
            visited.add(node_id)
            result_ids.append(node_id)
            if direction == "down":
                neighbors = [tgt for _, tgt, d in G.out_edges(node_id, data=True)
                             if d.get("relation") == "calls"]
            else:
                neighbors = [src for src, _, d in G.in_edges(node_id, data=True)
                             if d.get("relation") == "calls"]
            for nbr in neighbors:
                _dfs(nbr, remaining - 1)

        for start_id in start_ids:
            _dfs(start_id, depth)

        return [self._id_to_chunk[i] for i in result_ids if i in self._id_to_chunk]

    def find_dead_symbols(
        self,
        G: nx.DiGraph,
        exclude_types: Optional[set[str]] = None,
    ) -> list[dict]:
        """
        Return chunks that have no incoming 'calls' edges — i.e. nothing in
        the indexed code calls them.  These are potential dead / orphan code.

        Excludes:
          - __init__, __str__, __repr__, main  (always-valid entry points)
          - Classes and widgets (they're instantiated, not "called" in this graph)
          - Routes (called by HTTP, not internal code)
        """
        always_valid = {"__init__", "__str__", "__repr__", "__main__",
                        "main", "setUp", "tearDown", "test"}
        if exclude_types is None:
            exclude_types = {"class", "widget", "route", "interface", "struct",
                             "enum", "type_alias", "mixin", "extension"}

        dead = []
        for node_id in G.nodes():
            chunk = self._id_to_chunk.get(node_id)
            if not chunk:
                continue
            sym_type = chunk.get("type", "")
            if sym_type in exclude_types:
                continue
            name = chunk.get("symbol", "")
            if name in always_valid or name.startswith("test_"):
                continue

            incoming_calls = [
                src for src, _, d in G.in_edges(node_id, data=True)
                if d.get("relation") == "calls"
            ]
            if not incoming_calls:
                dead.append(chunk)

        return dead

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _resolve(self, name: str, prefer_file: str = "") -> list[str]:
        """
        Resolve a symbol name to chunk IDs.  Prefer same-file matches.
        Returns at most 3 IDs to keep the graph manageable.
        """
        ids = self._name_to_ids.get(name, [])
        if not ids:
            return []
        if prefer_file:
            same_file = [i for i in ids
                         if self._id_to_chunk.get(i, {}).get("file", "") == prefer_file]
            if same_file:
                return same_file[:1]
        return ids[:3]

    def _add_generic_edges(self, G: nx.DiGraph) -> None:
        """
        For non-Python chunks (TypeScript, Dart, Go …) that have no AST call
        data, scan the code text for occurrences of other symbol names.
        Only add edges where confidence is reasonable: the name must appear
        as a whole word (not as a substring).
        """
        # Skip Python chunks — they already have precise AST call data
        non_python = [
            c for c in self.chunks
            if not c.get("file", "").endswith(".py")
        ]
        if not non_python:
            return

        # Build pattern for all known symbol names (sorted longest-first to
        # avoid prefix matches)
        all_names = sorted(self._name_to_ids.keys(), key=len, reverse=True)
        if not all_names:
            return

        # Only match names that are > 3 chars to avoid false positives
        meaningful = [n for n in all_names if len(n) > 3][:500]
        # Use word-boundary regex for each
        patterns = {name: re.compile(r"\b" + re.escape(name) + r"\b")
                    for name in meaningful}

        for chunk in non_python:
            code    = chunk.get("code", "")
            sym     = chunk.get("symbol", "")
            if not code:
                continue

            caller_id = chunk["id"]
            caller_file = chunk.get("file", "")

            for name, pat in patterns.items():
                if name == sym:
                    continue
                if pat.search(code):
                    callee_ids = self._resolve(name, caller_file)
                    for callee_id in callee_ids:
                        if callee_id != caller_id:
                            G.add_edge(caller_id, callee_id, relation="calls")
