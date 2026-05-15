
import re
from pathlib import Path


class GoParser:
    """
    Regex-based Go source parser.

    Extracts:
      - top-level functions and methods (with receiver type)
      - struct type declarations
      - interface type declarations
      - const / var blocks (as named symbols)
    """

    _RE_FUNC = re.compile(
        r"^func\s+"
        r"(?:\((?P<receiver>[^)]+)\)\s+)?"   # optional method receiver
        r"(?P<name>\w+)\s*"
        r"(?P<generics>\[[^\]]*\])?\s*"
        r"\((?P<params>[^)]*)\)"
        r"(?:\s*\((?P<multi_ret>[^)]*)\)|\s*(?P<single_ret>[^\{]+))?"
        r"\s*\{",
        re.MULTILINE,
    )

    _RE_STRUCT = re.compile(
        r"^type\s+(?P<name>\w+)\s+struct\s*\{",
        re.MULTILINE,
    )

    _RE_INTERFACE = re.compile(
        r"^type\s+(?P<name>\w+)\s+interface\s*\{",
        re.MULTILINE,
    )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def parse(self, file_path: str) -> dict:
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return {"symbols": []}

        lines      = content.splitlines()
        line_index = self._build_line_index(content)
        symbols: list[dict] = []

        for m in self._RE_FUNC.finditer(content):
            name     = m.group("name")
            receiver = (m.group("receiver") or "").strip()
            start    = line_index(m.start())
            end      = self._find_block_end(lines, start - 1)
            # Derive class_name from receiver  e.g. "(s *Server)" → "Server"
            class_name = ""
            if receiver:
                parts = receiver.split()
                if len(parts) >= 2:
                    class_name = parts[-1].lstrip("*")
                elif len(parts) == 1:
                    class_name = parts[0].lstrip("*")

            sym_type = "method" if class_name else "function"
            symbols.append({
                "name":        name,
                "type":        sym_type,
                "start_line":  start,
                "end_line":    end,
                "decorators":  [],
                "docstring":   self._extract_comment(lines, start - 2),
                "parameters":  [],
                "return_type": "",
                "class_name":  class_name,
                "base_classes": [],
            })

        for m in self._RE_STRUCT.finditer(content):
            start = line_index(m.start())
            symbols.append({
                "name":        m.group("name"),
                "type":        "struct",
                "start_line":  start,
                "end_line":    self._find_block_end(lines, start - 1),
                "decorators":  [],
                "docstring":   self._extract_comment(lines, start - 2),
                "parameters":  [],
                "return_type": "",
                "class_name":  "",
                "base_classes": [],
            })

        for m in self._RE_INTERFACE.finditer(content):
            start = line_index(m.start())
            symbols.append({
                "name":        m.group("name"),
                "type":        "interface",
                "start_line":  start,
                "end_line":    self._find_block_end(lines, start - 1),
                "decorators":  [],
                "docstring":   self._extract_comment(lines, start - 2),
                "parameters":  [],
                "return_type": "",
                "class_name":  "",
                "base_classes": [],
            })

        return {"symbols": symbols}

    # ------------------------------------------------------------------ #
    # Utility helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_comment(lines: list[str], end_idx: int) -> str:
        comment_lines = []
        i = end_idx
        while i >= 0 and i >= end_idx - 5:
            stripped = lines[i].strip()
            if stripped.startswith("//"):
                comment_lines.insert(0, stripped[2:].strip())
                i -= 1
            else:
                break
        return " ".join(comment_lines).strip()

    @staticmethod
    def _build_line_index(content: str):
        newlines = [0]
        for i, ch in enumerate(content):
            if ch == "\n":
                newlines.append(i + 1)
        def get_line(offset: int) -> int:
            lo, hi = 0, len(newlines) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if newlines[mid] <= offset:
                    lo = mid
                else:
                    hi = mid - 1
            return lo + 1
        return get_line

    @staticmethod
    def _find_block_end(lines: list[str], start_idx: int, max_scan: int = 200) -> int:
        depth = 0
        for i in range(start_idx, min(len(lines), start_idx + max_scan)):
            depth += lines[i].count("{") - lines[i].count("}")
            if depth == 0 and i > start_idx:
                return i + 1
        return start_idx + 2
