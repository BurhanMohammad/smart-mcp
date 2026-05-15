
"""
JavaParser
==========

Regex-based Java source parser.

Extracts:
  - classes (including abstract, final, generics, implements/extends)
  - interfaces
  - enums
  - methods (including annotations, access modifiers, return types, params)
  - common Spring / Jakarta annotations → type reclassification
    (@RestController, @GetMapping, @Service, @Repository, @Entity …)
  - Javadoc first-line → docstring

Regex approach is chosen over a full Java grammar because:
  - zero runtime dependencies
  - handles malformed/partial files gracefully
  - fast enough for files up to ~5 k lines
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


# ── compiled patterns ────────────────────────────────────────────────── #

_ANNOTATION  = re.compile(r'^\s*(@[\w.]+(?:\(.*?\))?)\s*$')
_CLASS       = re.compile(
    r'^\s*(?:(?:public|protected|private|abstract|final|static)\s+)*'
    r'(class|interface|enum|record)\s+'
    r'([\w$<>,\s]+?)'          # name + optional generics
    r'(?:\s+(?:extends|implements)\s+[\w$<>.,\s]+)?'
    r'\s*\{',
    re.MULTILINE,
)
_METHOD      = re.compile(
    r'^\s*(?:(?:public|protected|private|static|final|abstract|synchronized|native|default|override)\s+)*'
    r'(?:(?:<[\w,\s]+>\s+)?)'  # generics
    r'([\w$<>\[\]]+(?:<[\w,\s<>]+>)?)\s+'  # return type
    r'([\w$]+)\s*'             # method name
    r'\(([^)]*)\)\s*'          # parameters
    r'(?:throws\s+[\w$,\s]+\s*)?'
    r'(?:\{|;)',
    re.MULTILINE,
)
_JAVADOC     = re.compile(r'/\*\*(.*?)\*/', re.DOTALL)
_SINGLE_LINE = re.compile(r'//\s*(.*)')

# Spring / Jakarta annotation → semantic type
_SPRING_MAP = {
    "@restcontroller": "rest_controller",
    "@controller":     "controller",
    "@getmapping":     "route",
    "@postmapping":    "route",
    "@putmapping":     "route",
    "@deletemapping":  "route",
    "@patchmapping":   "route",
    "@requestmapping": "route",
    "@service":        "service",
    "@repository":     "repository",
    "@component":      "component",
    "@entity":         "model",
    "@table":          "model",
    "@test":           "test",
    "@before":         "test_setup",
    "@after":          "test_teardown",
}


class JavaParser:
    """Parse a Java source file and return a list of symbol dicts."""

    def parse(self, file_path: str) -> dict:
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return {"symbols": []}

        lines   = content.splitlines()
        symbols = []

        self._extract_classes(content, lines, symbols)
        self._extract_methods(content, lines, symbols, file_path)
        return {"symbols": symbols}

    # ------------------------------------------------------------------ #

    def _extract_classes(
        self, content: str, lines: list[str], symbols: list[dict]
    ) -> None:
        for m in _CLASS.finditer(content):
            kw      = m.group(1)           # class / interface / enum / record
            name    = m.group(2).split("<")[0].strip()
            start   = content[: m.start()].count("\n") + 1
            end     = self._find_block_end(lines, start - 1)
            annots  = self._preceding_annotations(lines, start - 1)
            doc     = self._preceding_javadoc(content, m.start())

            sym_type = {"interface": "interface", "enum": "enum"}.get(kw, "class")
            for a in annots:
                mapped = _SPRING_MAP.get(a.lower().split("(")[0])
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

    def _extract_methods(
        self,
        content: str,
        lines: list[str],
        symbols: list[dict],
        file_path: str,
    ) -> None:
        class_name = ""
        # Determine enclosing class by scanning forward (simple heuristic)
        for m in _METHOD.finditer(content):
            return_type = m.group(1)
            name        = m.group(2)
            params_raw  = m.group(3).strip()
            start       = content[: m.start()].count("\n") + 1
            end         = self._find_block_end(lines, start - 1)
            annots      = self._preceding_annotations(lines, start - 1)
            doc         = self._preceding_javadoc(content, m.start())
            params      = self._parse_params(params_raw)

            # Skip constructor-like matches with uppercase-only names
            # (captured as class already)
            if return_type[0].isupper() and return_type == name:
                continue

            sym_type = "method"
            for a in annots:
                mapped = _SPRING_MAP.get(a.lower().split("(")[0])
                if mapped:
                    sym_type = mapped
                    break
            if any("@test" in a.lower() for a in annots):
                sym_type = "test"

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
                "class_name":  class_name,
            })

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_block_end(lines: list[str], start_idx: int) -> int:
        """Find the closing brace for the block starting at *start_idx*."""
        depth = 0
        for i in range(start_idx, len(lines)):
            depth += lines[i].count("{") - lines[i].count("}")
            if depth <= 0 and i > start_idx:
                return i + 1
        return len(lines)

    @staticmethod
    def _preceding_annotations(lines: list[str], start_idx: int) -> list[str]:
        """Collect `@Annotation` lines immediately above *start_idx*."""
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
    def _preceding_javadoc(content: str, pos: int) -> str:
        """Return the first sentence of the Javadoc comment before *pos*."""
        before = content[:pos]
        m = list(_JAVADOC.finditer(before))
        if not m:
            return ""
        last = m[-1]
        if pos - last.end() > 200:
            return ""
        raw = last.group(1).strip()
        # Remove leading * from each line
        lines = [ln.lstrip().lstrip("*").strip() for ln in raw.splitlines()]
        text  = " ".join(ln for ln in lines if ln)
        # Return first sentence only
        sentence = text.split(".")[0]
        return sentence.strip()[:200]

    @staticmethod
    def _parse_params(raw: str) -> list[str]:
        """Extract parameter names from a raw param string like 'String name, int age'."""
        if not raw:
            return []
        params = []
        for part in raw.split(","):
            tokens = part.strip().split()
            if tokens:
                params.append(tokens[-1].strip("[]"))
        return [p for p in params if p and p.isidentifier()]
