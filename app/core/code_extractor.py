
from pathlib import Path


class CodeExtractor:
    """
    Reads actual source-code lines from a file for a given symbol range.

    Used by ASTChunker so every indexed chunk carries real code rather than
    just a symbol name + type label.
    """

    _cache: dict[str, list[str]] = {}

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def extract(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        max_lines: int = 80,
    ) -> str:
        """
        Return source code lines [start_line, end_line] (1-based, inclusive).

        If the symbol is longer than *max_lines* we keep the first *max_lines*
        rows plus a trailing ellipsis so the chunk stays token-efficient.
        """
        lines = self._read_lines(file_path)
        if not lines:
            return ""

        s = max(0, start_line - 1)
        e = min(len(lines), end_line)

        chunk = lines[s:e]

        if len(chunk) > max_lines:
            chunk = chunk[:max_lines]
            chunk.append("    # … (truncated)")

        return "\n".join(chunk)

    def extract_context(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        context_lines: int = 3,
        max_lines: int = 80,
    ) -> str:
        """
        Like *extract* but includes a few leading context lines so the AI can
        see imports / decorators that live just above the symbol.
        """
        lines = self._read_lines(file_path)
        if not lines:
            return ""

        s = max(0, start_line - 1 - context_lines)
        e = min(len(lines), end_line)

        chunk = lines[s:e]

        if len(chunk) > max_lines:
            chunk = chunk[:max_lines]
            chunk.append("    # … (truncated)")

        return "\n".join(chunk)

    def get_line(self, file_path: str, line_number: int) -> str:
        """Return a single line (1-based). Returns '' if out of range."""
        lines = self._read_lines(file_path)
        if not lines or line_number < 1 or line_number > len(lines):
            return ""
        return lines[line_number - 1]

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _read_lines(self, file_path: str) -> list[str]:
        """Read and cache file lines. Returns [] on error."""
        if file_path in self._cache:
            return self._cache[file_path]
        try:
            text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            result = text.splitlines()
            # Cap cache size to avoid memory bloat on very large repos
            if len(self._cache) > 500:
                self._cache.clear()
            self._cache[file_path] = result
            return result
        except Exception:
            return []

    def invalidate(self, file_path: str) -> None:
        """Remove *file_path* from the line cache (call after file changes)."""
        self._cache.pop(file_path, None)
