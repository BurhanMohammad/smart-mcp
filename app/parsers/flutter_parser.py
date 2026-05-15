
import re
from pathlib import Path


class FlutterParser:
    """
    Dart / Flutter parser using regex.

    Extracts:
      - class declarations (Widget subclasses flagged separately)
      - top-level functions and methods
      - StatelessWidget / StatefulWidget subclasses
      - build() method blocks
      - named constructors
      - mixins and extensions
    """

    _RE_CLASS = re.compile(
        r"^(?:abstract\s+)?class\s+(?P<name>\w+)"
        r"(?:\s+extends\s+(?P<base>[\w<>, ]+?))?"
        r"(?:\s+(?:implements|with)\s+[\w<>, ]+?)?"
        r"\s*\{",
        re.MULTILINE,
    )

    _RE_MIXIN = re.compile(r"^mixin\s+(?P<name>\w+)", re.MULTILINE)

    _RE_EXTENSION = re.compile(r"^extension\s+(?P<name>\w+)\s+on\s+(?P<on_type>\w+)", re.MULTILINE)

    _RE_FUNCTION = re.compile(
        r"^(?P<annotations>(?:\s*@\w+\s*\n)*)"      # optional annotations
        r"(?:(?:static|async|@override)\s+)*"
        r"(?:[\w<>\[\]?]+\s+)+?"                     # return type (optional)
        r"(?P<name>\w+)\s*"
        r"(?P<generics><[^>]*>)?\s*"
        r"\((?P<params>[^)]*)\)\s*"
        r"(?:async\s*)?(?:\{|=>)",
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

        self._extract_classes(content, lines, line_index, symbols)
        self._extract_mixins(content, lines, line_index, symbols)
        self._extract_extensions(content, lines, line_index, symbols)
        self._extract_functions(content, lines, line_index, symbols)

        return {"symbols": symbols}

    # ------------------------------------------------------------------ #
    # Extraction helpers                                                   #
    # ------------------------------------------------------------------ #

    def _extract_classes(self, content, lines, line_index, symbols):
        widget_bases = {
            "StatelessWidget", "StatefulWidget", "State", "Widget",
            "InheritedWidget", "RenderObjectWidget",
        }
        for m in self._RE_CLASS.finditer(content):
            name  = m.group("name")
            base  = (m.group("base") or "").strip().split("<")[0].strip()
            start = line_index(m.start())
            end   = self._find_block_end(lines, start - 1)
            sym_type = "widget" if base in widget_bases else "class"
            symbols.append({
                "name":        name,
                "type":        sym_type,
                "start_line":  start,
                "end_line":    end,
                "decorators":  [],
                "docstring":   "",
                "parameters":  [],
                "return_type": "",
                "class_name":  "",
                "base_classes": [base] if base else [],
            })

    def _extract_mixins(self, content, lines, line_index, symbols):
        for m in self._RE_MIXIN.finditer(content):
            start = line_index(m.start())
            symbols.append({
                "name":        m.group("name"),
                "type":        "mixin",
                "start_line":  start,
                "end_line":    self._find_block_end(lines, start - 1),
                "decorators":  [],
                "docstring":   "",
                "parameters":  [],
                "return_type": "",
                "class_name":  "",
                "base_classes": [],
            })

    def _extract_extensions(self, content, lines, line_index, symbols):
        for m in self._RE_EXTENSION.finditer(content):
            start = line_index(m.start())
            symbols.append({
                "name":        m.group("name"),
                "type":        "extension",
                "start_line":  start,
                "end_line":    self._find_block_end(lines, start - 1),
                "decorators":  [],
                "docstring":   f"extension on {m.group('on_type')}",
                "parameters":  [],
                "return_type": "",
                "class_name":  "",
                "base_classes": [m.group("on_type")],
            })

    def _extract_functions(self, content, lines, line_index, symbols):
        seen = {s["name"] for s in symbols}
        for m in self._RE_FUNCTION.finditer(content):
            name = m.group("name")
            if name in seen or name in {
                "if", "else", "for", "while", "switch", "return",
                "class", "import", "export", "void", "final", "var",
            }:
                continue
            start   = line_index(m.start())
            end     = self._find_block_end(lines, start - 1)
            params  = [p.split()[-1] for p in m.group("params").split(",") if p.strip()]
            annots  = [a.strip() for a in (m.group("annotations") or "").split() if a.startswith("@")]
            symbols.append({
                "name":        name,
                "type":        "function",
                "start_line":  start,
                "end_line":    end,
                "decorators":  annots,
                "docstring":   "",
                "parameters":  params,
                "return_type": "",
                "class_name":  "",
                "base_classes": [],
            })

    # ------------------------------------------------------------------ #
    # Utility helpers                                                      #
    # ------------------------------------------------------------------ #

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
    def _find_block_end(lines: list[str], start_idx: int, max_scan: int = 300) -> int:
        depth = 0
        for i in range(start_idx, min(len(lines), start_idx + max_scan)):
            depth += lines[i].count("{") - lines[i].count("}")
            if depth == 0 and i > start_idx:
                return i + 1
        return start_idx + 2
