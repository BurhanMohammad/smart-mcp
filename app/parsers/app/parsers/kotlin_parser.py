
"""
KotlinParser
============

Regex-based Kotlin source parser.

Extracts:
  - classes, data classes, sealed classes, abstract classes, objects, companions
  - interfaces
  - functions (including suspend, inline, extension functions)
  - properties (val / var at top level or class level)
  - common Android / Ktor / Spring annotations:
    @Composable, @ViewModel, @GET, @POST, @Route, @Test …

"""

from __future__ import annotations

import re
from pathlib import Path


# ── compiled patterns ────────────────────────────────────────────────── #

_ANNOTATION = re.compile(r'^\s*(@[\w.]+(?:\(.*?\))?)\s*$')

_CLASS = re.compile(
    r'^\s*(?:(?:public|internal|private|protected|open|abstract|sealed|data|inner|enum)\s+)*'
    r'(class|interface|object|companion object)\s+'
    r'([\w$]+)'
    r'(?:[^{;]*)?'
    r'\s*[\{:]',
    re.MULTILINE,
)

_FUN = re.compile(
    r'^\s*(?:(?:public|internal|private|protected|open|override|inline|suspend|operator|infix|external|actual|expect)\s+)*'
    r'fun\s+'
    r'(?:<[^>]*>\s+)?'           # optional generics
    r'(?:([\w$]+)\.)?'           # optional extension receiver
    r'([\w$`]+)\s*'              # function name (backtick-quoted allowed)
    r'\(([^)]*)\)'               # parameters
    r'(?:\s*:\s*([\w$<>?,\s\[\]]+))?'  # optional return type
    r'\s*[{=]',
    re.MULTILINE,
)

# Annotation → semantic type
_ANNOT_MAP = {
    "@composable":        "composable",
    "@preview":           "preview",
    "@get":               "route",
    "@post":              "route",
    "@put":               "route",
    "@delete":            "route",
    "@route":             "route",
    "@getmapping":        "route",
    "@postmapping":       "route",
    "@requestmapping":    "route",
    "@test":              "test",
    "@before":            "test_setup",
    "@after":             "test_teardown",
    "@viewmodel":         "viewmodel",
    "@hiltviewmodel":     "viewmodel",
    "@androidentrypoint": "activity",
    "@service":           "service",
    "@repository":        "repository",
    "@entity":            "model",
}


class KotlinParser:
    """Parse a Kotlin source file and return a list of symbol dicts."""

    def parse(self, file_path: str) -> dict:
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return {"symbols": []}

        lines   = content.splitlines()
        symbols = []

        self._extract_classes(content, lines, symbols)
        self._extract_functions(content, lines, symbols)
        return {"symbols": symbols}

    # ------------------------------------------------------------------ #

    def _extract_classes(
        self, content: str, lines: list[str], symbols: list[dict]
    ) -> None:
        for m in _CLASS.finditer(content):
            kw      = m.group(1)   # class / interface / object / companion object
            name    = m.group(2)
            start   = content[: m.start()].count("\n") + 1
            end     = self._find_block_end(lines, start - 1)
            annots  = self._preceding_annotations(lines, start - 1)
            doc     = self._preceding_kdoc(content, m.start())

            sym_type = {"interface": "interface", "object": "object"}.get(kw, "class")
            for a in annots:
                mapped = _ANNOT_MAP.get(a.lower().split("(")[0])
                if mapped:
                    sym_type = mapped
                    break

            symbols.append({
                "name":        name,
                "type":        sym_type,
                "start_line":  start,
                "end_line":    end,
                "decorators":  annots,
                "docstring":   doc,
                "base_classes": [],
                "parameters":  [],
                "return_type": "",
                "class_name":  "",
            })

    def _extract_functions(
        self, content: str, lines: list[str], symbols: list[dict]
    ) -> None:
        for m in _FUN.finditer(content):
            receiver    = m.group(1) or ""   # e.g. "String" for extension fun
            name        = m.group(2).strip("`")
            params_raw  = m.group(3).strip()
            return_type = (m.group(4) or "").strip()
            start       = content[: m.start()].count("\n") + 1
            end         = self._find_block_end(lines, start - 1)
            annots      = self._preceding_annotations(lines, start - 1)
            doc         = self._preceding_kdoc(content, m.start())
            params      = self._parse_params(params_raw)

            sym_type = "function"
            for a in annots:
                mapped = _ANNOT_MAP.get(a.lower().split("(")[0])
                if mapped:
                    sym_type = mapped
                    break

            # Mark as extension function if receiver present
            if receiver:
                sym_type = "extension_function"

            symbols.append({
                "name":        name,
                "type":        sym_type,
                "start_line":  start,
                "end_line":    end,
                "decorators":  annots,
                "docstring":   doc,
                "base_classes": [],
                "parameters":  params,
                "return_type": return_type,
                "class_name":  receiver,
            })

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_block_end(lines: list[str], start_idx: int) -> int:
        depth = 0
        for i in range(start_idx, len(lines)):
            depth += lines[i].count("{") - lines[i].count("}")
            if depth <= 0 and i > start_idx:
                return i + 1
        return len(lines)

    @staticmethod
    def _preceding_annotations(lines: list[str], start_idx: int) -> list[str]:
        annots: list[str] = []
        i = start_idx - 1
        while i >= 0:
            stripped = lines[i].strip()
            if stripped.startswith("@"):
                annots.insert(0, stripped)
            elif stripped and not stripped.startswith("//"):
                break
            i -= 1
        return annots

    @staticmethod
    def _preceding_kdoc(content: str, pos: int) -> str:
        """Return first sentence of the KDoc (/** … */) comment before *pos*."""
        before = content[:pos]
        m = list(re.finditer(r'/\*\*(.*?)\*/', before, re.DOTALL))
        if not m:
            return ""
        last = m[-1]
        if pos - last.end() > 300:
            return ""
        raw   = last.group(1)
        lines = [ln.lstrip().lstrip("*").strip() for ln in raw.splitlines()]
        text  = " ".join(ln for ln in lines if ln)
        return text.split(".")[0].strip()[:200]

    @staticmethod
    def _parse_params(raw: str) -> list[str]:
        """Extract param names from e.g. 'name: String, age: Int = 0'."""
        if not raw:
            return []
        params = []
        for part in raw.split(","):
            part = part.strip()
            if ":" in part:
                params.append(part.split(":")[0].strip().lstrip("val ").lstrip("var "))
            elif part:
                params.append(part.split()[0])
        return [p for p in params if p and (p.isidentifier() or p.startswith("_"))]
