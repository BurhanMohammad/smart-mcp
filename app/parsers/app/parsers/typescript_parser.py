
import re
from pathlib import Path


class TypeScriptParser:
    """
    Regex-based TypeScript / JavaScript / JSX / TSX parser.

    Extracts:
      - named functions (function foo() / async function foo())
      - arrow functions assigned to a const  (const foo = () => …)
      - exported default functions
      - class declarations with optional base class
      - interface / type alias declarations
      - enum declarations
      - React functional components (const Foo: React.FC = …)
      - Express / Next.js / Fastify route handlers
        (app.get('/path', handler), router.post(…))

    All symbols carry start_line, end_line so the ASTChunker can pull real code.
    """

    # ------------------------------------------------------------------ #
    # Regex patterns                                                       #
    # ------------------------------------------------------------------ #

    _RE_NAMED_FN = re.compile(
        r"^(?P<export>export\s+)?(?P<async>async\s+)?function\s+(?P<name>\w+)\s*"
        r"(?P<generics><[^>]*>)?\s*\((?P<params>[^)]*)\)"
        r"(?:\s*:\s*(?P<ret>[^\{]+?))?",
        re.MULTILINE,
    )

    _RE_ARROW_FN = re.compile(
        r"^(?P<export>export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*"
        r"(?::\s*(?:React\.FC|FC|React\.FunctionComponent|FunctionComponent)"
        r"(?:<[^>]*>)?)?\s*=\s*(?:async\s+)?\(",
        re.MULTILINE,
    )

    _RE_CLASS = re.compile(
        r"^(?:export\s+)?(?:abstract\s+)?class\s+(?P<name>\w+)"
        r"(?:\s+extends\s+(?P<base>\w+))?",
        re.MULTILINE,
    )

    _RE_INTERFACE = re.compile(
        r"^(?:export\s+)?interface\s+(?P<name>\w+)(?:\s+extends\s+[\w,\s]+)?",
        re.MULTILINE,
    )

    _RE_TYPE_ALIAS = re.compile(
        r"^(?:export\s+)?type\s+(?P<name>\w+)\s*(?:<[^>]*>)?\s*=",
        re.MULTILINE,
    )

    _RE_ENUM = re.compile(
        r"^(?:export\s+)?(?:const\s+)?enum\s+(?P<name>\w+)",
        re.MULTILINE,
    )

    _RE_ROUTE = re.compile(
        r"(?:app|router|server|fastify)\s*\.\s*(?P<method>get|post|put|patch|delete|options|head)\s*"
        r"\(\s*['\"](?P<path>[^'\"]+)['\"]",
        re.MULTILINE | re.IGNORECASE,
    )

    _RE_NEXT_EXPORT = re.compile(
        r"export\s+(?:default\s+)?(?:async\s+)?function\s+(?P<name>getServerSideProps|getStaticProps"
        r"|getStaticPaths|default|\w+)\s*\(",
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

        self._extract_named_functions(content, lines, line_index, symbols)
        self._extract_arrow_functions(content, lines, line_index, symbols)
        self._extract_classes(content, lines, line_index, symbols)
        self._extract_interfaces(content, lines, line_index, symbols)
        self._extract_type_aliases(content, lines, line_index, symbols)
        self._extract_enums(content, lines, line_index, symbols)
        self._extract_routes(content, lines, line_index, symbols)

        return {"symbols": symbols}

    # ------------------------------------------------------------------ #
    # Extraction helpers                                                   #
    # ------------------------------------------------------------------ #

    def _extract_named_functions(self, content, lines, line_index, symbols):
        for m in self._RE_NAMED_FN.finditer(content):
            name      = m.group("name")
            start     = line_index(m.start())
            end_line  = self._find_block_end(lines, start - 1)
            params    = [p.strip().split(":")[0].strip()
                         for p in m.group("params").split(",") if p.strip()]
            ret_type  = (m.group("ret") or "").strip()
            sym_type  = "async_function" if m.group("async") else "function"
            exported  = bool(m.group("export"))
            symbols.append({
                "name":        name,
                "type":        sym_type,
                "start_line":  start,
                "end_line":    end_line,
                "parameters":  params,
                "return_type": ret_type,
                "decorators":  ["@export"] if exported else [],
                "class_name":  "",
                "base_classes": [],
                "docstring":   self._extract_jsdoc(lines, start - 2),
            })

    def _extract_arrow_functions(self, content, lines, line_index, symbols):
        for m in self._RE_ARROW_FN.finditer(content):
            name     = m.group("name")
            start    = line_index(m.start())
            end_line = self._find_block_end(lines, start - 1)
            exported = bool(m.group("export"))
            # Skip if already captured as named function
            if any(s["name"] == name for s in symbols):
                continue
            symbols.append({
                "name":        name,
                "type":        "arrow_function",
                "start_line":  start,
                "end_line":    end_line,
                "parameters":  [],
                "return_type": "",
                "decorators":  ["@export"] if exported else [],
                "class_name":  "",
                "base_classes": [],
                "docstring":   self._extract_jsdoc(lines, start - 2),
            })

    def _extract_classes(self, content, lines, line_index, symbols):
        for m in self._RE_CLASS.finditer(content):
            name       = m.group("name")
            base       = m.group("base") or ""
            start      = line_index(m.start())
            end_line   = self._find_block_end(lines, start - 1)
            symbols.append({
                "name":        name,
                "type":        "class",
                "start_line":  start,
                "end_line":    end_line,
                "parameters":  [],
                "return_type": "",
                "decorators":  [],
                "class_name":  "",
                "base_classes": [base] if base else [],
                "docstring":   self._extract_jsdoc(lines, start - 2),
            })

    def _extract_interfaces(self, content, lines, line_index, symbols):
        for m in self._RE_INTERFACE.finditer(content):
            start    = line_index(m.start())
            end_line = self._find_block_end(lines, start - 1)
            symbols.append({
                "name":        m.group("name"),
                "type":        "interface",
                "start_line":  start,
                "end_line":    end_line,
                "parameters":  [],
                "return_type": "",
                "decorators":  [],
                "class_name":  "",
                "base_classes": [],
                "docstring":   "",
            })

    def _extract_type_aliases(self, content, lines, line_index, symbols):
        for m in self._RE_TYPE_ALIAS.finditer(content):
            start = line_index(m.start())
            symbols.append({
                "name":        m.group("name"),
                "type":        "type_alias",
                "start_line":  start,
                "end_line":    start,
                "parameters":  [],
                "return_type": "",
                "decorators":  [],
                "class_name":  "",
                "base_classes": [],
                "docstring":   "",
            })

    def _extract_enums(self, content, lines, line_index, symbols):
        for m in self._RE_ENUM.finditer(content):
            start    = line_index(m.start())
            end_line = self._find_block_end(lines, start - 1)
            symbols.append({
                "name":        m.group("name"),
                "type":        "enum",
                "start_line":  start,
                "end_line":    end_line,
                "parameters":  [],
                "return_type": "",
                "decorators":  [],
                "class_name":  "",
                "base_classes": [],
                "docstring":   "",
            })

    def _extract_routes(self, content, lines, line_index, symbols):
        for m in self._RE_ROUTE.finditer(content):
            start = line_index(m.start())
            name  = f"{m.group('method').upper()} {m.group('path')}"
            symbols.append({
                "name":        name,
                "type":        "route",
                "start_line":  start,
                "end_line":    self._find_block_end(lines, start - 1),
                "parameters":  [],
                "return_type": "",
                "decorators":  [f"@{m.group('method').lower()}"],
                "class_name":  "",
                "base_classes": [],
                "docstring":   "",
                "route_url":   m.group("path"),
            })

    # ------------------------------------------------------------------ #
    # Utility helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_line_index(content: str):
        """Return a callable: offset → 1-based line number."""
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
        """
        Naively find the closing brace of a block starting at *start_idx* (0-based).
        Returns 1-based line number.  Falls back to start+1 on failure.
        """
        depth = 0
        for i in range(start_idx, min(len(lines), start_idx + max_scan)):
            depth += lines[i].count("{") - lines[i].count("}")
            if depth > 0 and i > start_idx:
                if depth == 0:
                    return i + 1
            if depth == 0 and i > start_idx:
                return i + 1
        return start_idx + 2  # fallback: at least one line

    @staticmethod
    def _extract_jsdoc(lines: list[str], end_idx: int) -> str:
        """
        Walk backwards from *end_idx* looking for a /** ... */ comment block.
        Returns the comment text or ''.
        """
        if end_idx < 0:
            return ""
        comment_lines = []
        i = end_idx
        while i >= 0 and i >= end_idx - 10:
            stripped = lines[i].strip()
            if stripped.startswith("*") or stripped.startswith("/**") or stripped.startswith("*/"):
                comment_lines.insert(0, stripped.lstrip("*/ "))
                i -= 1
            else:
                break
        return " ".join(comment_lines).strip()
