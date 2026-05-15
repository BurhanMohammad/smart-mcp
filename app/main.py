
"""
SmartMCP — Main Indexer
=======================

Orchestrates the full indexing pipeline:

  1.  Detect framework
  2.  Scan files
  3.  Filter changed files via IncrementalIndexer
  4.  Parse symbols (Python / TypeScript / Flutter / Go)
  5.  Build AST chunks with real source code
  6.  Build / reload HybridRetriever (BM25 + FAISS, persistent)
  7.  Map routes (Django, FastAPI, Flask, Express, Next.js)
  8.  Register everything in the MCP tool registry

Progress is reported via logging (visible in stderr) and optionally via
tqdm if it is installed.
"""

from __future__ import annotations

import datetime
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SmartMCP:
    """
    Parameters
    ----------
    repo_path : str
        Absolute path to the repository to index.
    cache_dir : str | None
        Directory to persist the FAISS index and file-hash cache.
        Defaults to  <repo_path>/.smart-mcp-cache/
    force_reindex : bool
        If True, ignore the incremental cache and re-index everything.
    """

    def __init__(
        self,
        repo_path: str,
        cache_dir: Optional[str] = None,
        force_reindex: bool = False,
    ):
        self.repo_path     = os.path.abspath(repo_path)
        # Load config — repo-level config overrides user-level and defaults
        from app.config import load_config
        self._cfg          = load_config(self.repo_path)
        self.cache_dir     = cache_dir or os.path.join(
            self.repo_path, self._cfg.cache_subdir
        )
        self.force_reindex = force_reindex

        # Lazy imports keep startup fast when used as a library
        from app.core.file_scanner      import FileScanner
        from app.core.framework_detector import FrameworkDetector
        from app.chunking.ast_chunker    import ASTChunker
        from app.core.incremental_indexer import IncrementalIndexer

        from app.parsers.python_parser     import PythonParser
        from app.parsers.typescript_parser import TypeScriptParser
        from app.parsers.flutter_parser    import FlutterParser
        from app.parsers.go_parser         import GoParser
        from app.parsers.java_parser       import JavaParser
        from app.parsers.kotlin_parser     import KotlinParser
        from app.parsers.rust_parser       import RustParser

        self.detector   = FrameworkDetector()
        self.scanner    = FileScanner()
        self.chunker    = ASTChunker()
        self.indexer    = IncrementalIndexer(cache_dir=self.cache_dir if not force_reindex else None)

        self._parsers = {
            # First-class support
            ".py":   PythonParser(),
            ".ts":   TypeScriptParser(),
            ".tsx":  TypeScriptParser(),
            ".js":   TypeScriptParser(),
            ".jsx":  TypeScriptParser(),
            ".dart": FlutterParser(),
            ".go":   GoParser(),
            # New parsers
            ".java": JavaParser(),
            ".kt":   KotlinParser(),
            ".kts":  KotlinParser(),
            ".rs":   RustParser(),
        }

    # ------------------------------------------------------------------ #
    # Public: build_index                                                  #
    # ------------------------------------------------------------------ #

    def build_index(self) -> None:
        """Full pipeline: scan → parse → embed → register."""
        started_at = datetime.datetime.now()
        logger.info(f"{'='*60}")
        logger.info(f"Smart-MCP indexing: {self.repo_path}")
        logger.info(f"Cache dir: {self.cache_dir}")

        # 1. Detect framework
        framework_info = self.detector.detect(self.repo_path)
        logger.info(
            f"Detected: language={framework_info['language']}, "
            f"framework={framework_info['framework']}"
        )

        # 2. Scan files
        all_files = self.scanner.scan(self.repo_path)
        logger.info(f"Found {len(all_files)} source files")

        # 3. Filter to changed files (incremental mode)
        if self.force_reindex:
            files_to_parse = all_files
            logger.info("Force re-index: parsing all files")
        else:
            files_to_parse = self.indexer.filter_changed(all_files)
            logger.info(
                f"Incremental: {len(files_to_parse)} files changed "
                f"(out of {len(all_files)})"
            )

        # 4. Parse symbols + build chunks
        chunks = self._parse_files(files_to_parse)

        # If incremental, merge with previously indexed chunks that haven't changed
        # (For now we rebuild everything; a full merge is a future improvement)
        if not chunks:
            logger.warning(
                "No chunks produced — check that source files contain "
                "parseable functions/classes."
            )
            # Still register an empty retriever so the server doesn't crash
            from app.core.hybrid_retriever import HybridRetriever
            retriever = HybridRetriever(
                [], cache_dir=self.cache_dir, model_name=self._cfg.embedding_model
            )
            self._register(retriever, [], framework_info, started_at, 0)
            return

        # 5. Build HybridRetriever (loads from disk if cache is valid)
        logger.info(f"Building retrieval index for {len(chunks)} chunks …")
        from app.core.hybrid_retriever import HybridRetriever
        retriever = HybridRetriever(
            chunks,
            cache_dir=self.cache_dir,
            model_name=self._cfg.embedding_model,
        )

        # 6. Route mapping
        logger.info("Mapping routes …")
        routes = self._extract_routes(framework_info["framework"])

        # 7. Register in MCP tool registry
        self._register(retriever, routes, framework_info, started_at, len(chunks))

        elapsed = (datetime.datetime.now() - started_at).total_seconds()
        logger.info(
            f"Index ready in {elapsed:.1f}s — "
            f"{len(chunks)} chunks, {len(routes)} routes."
        )
        logger.info("=" * 60)

    # ------------------------------------------------------------------ #
    # Internal: parsing                                                    #
    # ------------------------------------------------------------------ #

    def _parse_files(self, files: list[str]) -> list[dict]:
        chunks: list[dict] = []
        failed  = 0
        skipped = 0

        # Optional progress bar (degrades gracefully if tqdm not installed)
        try:
            from tqdm import tqdm
            iterator = tqdm(files, desc="Parsing", unit="file", ncols=80)
        except ImportError:
            iterator = files

        for file_path in iterator:
            suffix = Path(file_path).suffix.lower()
            parser = self._parsers.get(suffix)

            if parser is None:
                skipped += 1
                continue

            try:
                parsed  = parser.parse(file_path)
                symbols = parsed.get("symbols", [])

                # Assign unique IDs
                for symbol in symbols:
                    symbol["id"] = str(uuid.uuid4())

                file_chunks = self.chunker.chunk(file_path, symbols)
                chunks.extend(file_chunks)

            except Exception as exc:
                logger.debug(f"Parse failed: {file_path} → {exc}")
                failed += 1

        logger.info(
            f"Parsed {len(files)} files → "
            f"{len(chunks)} chunks  "
            f"({failed} failures, {skipped} skipped)"
        )
        return chunks

    # ------------------------------------------------------------------ #
    # Internal: route mapping                                              #
    # ------------------------------------------------------------------ #

    def _extract_routes(self, framework: str) -> list[dict]:
        try:
            from app.core.route_mapper import RouteMapper
            mapper = RouteMapper(self.repo_path, framework)
            routes = mapper.extract()
            logger.info(f"Route mapper: found {len(routes)} routes")
            return routes
        except Exception as exc:
            logger.warning(f"Route mapping failed: {exc}")
            return []

    # ------------------------------------------------------------------ #
    # Internal: registration                                               #
    # ------------------------------------------------------------------ #

    def _register(
        self,
        retriever,
        routes: list[dict],
        framework_info: dict,
        started_at: datetime.datetime,
        chunk_count: int,
    ) -> None:
        from app.mcp.tools import register_index
        meta = {
            "repo_path":   self.repo_path,
            "framework":   framework_info.get("framework", "unknown"),
            "language":    framework_info.get("language", "unknown"),
            "chunk_count": chunk_count,
            "indexed_at":  started_at.isoformat(timespec="seconds"),
        }
        register_index(retriever, routes, meta)


# ── CLI entry-point ─────────────────────────────────────────────────────── #

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="[smart-mcp] %(levelname)s: %(message)s",
    )

    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = input("Repository path: ").strip()

    force = "--force" in sys.argv or "-f" in sys.argv

    app = SmartMCP(path, force_reindex=force)
    app.build_index()

    print("\nIndex built. You can now start the MCP server:")
    print("  python -m app.mcp.server\n")
