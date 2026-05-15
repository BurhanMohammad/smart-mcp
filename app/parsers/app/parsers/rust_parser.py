
"""
RustParser
==========

Regex-based Rust source parser.

Extracts:
  - functions (including async, pub, unsafe, const, extern)
  - impl blocks — with `self` type and optional trait being implemented
  - structs, enums, traits, type aliases
  - common Actix-web / Axum / Rocket attributes:
    #[get(...)], #[post(...)], #[route(...)], #[tokio::main] …
  - /// and //! doc-comments → docstring
"""

from __future__ import annotations

import re
from pathlib import Path


# ── compiled patterns ────────────────────────────────────────────────── #

_DOC_COMMENT = re.compile(r'^\s*///\s?(.*)')

_ATTR = re.compile(r'^\s*(#\[[\w:]+(?:\(.*?\))?])\s*$')

_FN = re.compile(
    r'^\s*(?:(?:pub(?:\([^)]*\))?|async|unsafe|const|extern(?:\s+"[^"]*")?)\s+)*'
    r'fn\s+'
    r'([\w]+)'                   # function name
    r'(?:<[^>]*>)?'              # optional generics
    r'\s*\(([^)]*)\)'            # parameters
    r'(?:\s*->\s*([\w<>&\[\],\s:\']+))?'  # optional return type
    r'\s*(?:\{|where)',
    re.MULTILINE,
)

_IMPL = re.compile(
    r'^\s*impl(?:<[^>]*>)?\s+'
    r'(?:([\w:]+(?:<[^>]*>)?)\s+for\s+)?'   # optional Trait for
    r'([\w:]+(?:<[^>]*>)?)'                  # type name
    r'(?:\s+where[^{]+)?'
    r'\s*\{',
    re.MULTILINE,
)

_STRUCT = re.compile(
    r'^\s*(?:(?:pub(?:\([^)]*\))?)\s+)?'
    r'(struct|enum|trait|type)\s+'
    r'([\w]+)',
    re.MULTILINE,
)

# Attribute → semantic type
_ATTR_MAP = {
    "#[get":          "route",
    "#[post":         "route",
    "#[put":          "route",
    "#[delete":       "route",
    "#[patch":        "route",
    "#[route":        "route",
    "#[handler":      "route",
    "#[tokio::test":  "test",
    "#[test":         "test",
    "#[cfg(test":     "test_module",
    "#[tokio::main":  "entry_point",
    "#[actix_web::main": "entry_point",
}


class RustParser:
    """Parse a Rust source file and return a list of symbol dicts."""

    def parse(self, file_path: str) -> dict:
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return {"symbols": []}

        lines   = content.splitlines()
        symbols: list[dict] = []

        self._extract_structs(content, lines, symbols)
        self._extract_impls(content, lines, symbols)
        self._extract_functions(content, lines, symbols)
        return {"symbols": symbols}

    # ------------------------------------------------------------------ #

    def _extract_structs(
        self, content: str, lines: list[str], symbols: list[dict]
    ) -> None:
        for m in _STRUCT.finditer(content):
            kw    = m.group(1)    # struct / enum / trait / type
            name  = m.group(2)
            start = content[: m.start()].count("\n") + 1
            end   = self._find_block_end(lines, start - 1)
            attrs = self._preceding_attrs(lines, start - 1)
            doc   = self._preceding_doc(lines, start - 1)

            symbols.append({
                "name":        name,
                "type":        kw,
                "start_line":  start,
                "end_line":    end,
                "decorators":  attrs,
                "docstring":   doc,
                "base_classes": [],
                "parameters":  [],
                "return_type": "",
                "class_name":  "",
            })

    def _extract_impls(
        self, content: str, lines: list[str], symbols: list[dict]
    ) -> None:
        for m in _IMPL.finditer(content):
            trait_name = m.group(1) or ""
            type_name  = m.group(2)
            start      = content[: m.start()].count("\n") + 1
            end        = self._find_block_end(lines, start - 1)
            doc        = self._preceding_doc(lines, start - 1)

            name = f"impl {type_name}"
            if trait_name:
                name = f"impl {trait_name} for {type_name}"

            symbols.append({
                "name":        name,
                "type":        "impl",
                "start_line":  start,
                "end_line":    end,
                "decorators":  [],
                "docstring":   doc,
                "base_classes": [trait_name] if trait_name else [],
                "parameters":  [],
                "return_type": "",
                "class_name":  type_name,
            })

    def _extract_functions(
        self, content: str, lines: list[str], symbols: list[dict]
    ) -> None:
        for m in _FN.finditer(content):
            name        = m.group(1)
            params_raw  = m.group(2).strip()
            return_type = (m.group(3) or "").strip()
            start       = content[: m.start()].count("\n") + 1
            end         = self._find_block_end(lines, start - 1)
            attrs       = self._preceding_attrs(lines, start - 1)
            doc         = self._preceding_doc(lines, start - 1)
            params      = self._parse_params(params_raw)

            sym_type = "function"
            for a in attrs:
                for prefix, mapped in _ATTR_MAP.items():
                    if a.startswith(prefix):
                        sym_type = mapped
                        break

            symbols.append({
                "name":        name,
                "type":        sym_type,
                "start_line":  start,
                "end_line":    end,
                "decorators":  attrs,
                "docstring":   doc,
                "base_classes": [],
                "parameters":  params,
                "return_type": return_type,
                "class_name":  "",
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
    def _preceding_attrs(lines: list[str], start_idx: int) -> list[str]:
        """Collect #[attr] lines immediately above *start_idx*."""
        attrs: list[str] = []
        i = start_idx - 1
        while i >= 0:
            stripped = lines[i].strip()
            if stripped.startswith("#["):
                attrs.insert(0, stripped)
            elif stripped and not stripped.startswith("//"):
                break
            i -= 1
        return attrs

    @staticmethod
    def _preceding_doc(lines: list[str], start_idx: int) -> str:
        """Collect consecutive `///` lines immediately above *start_idx*."""
        doc_lines: list[str] = []
        i = start_idx - 1
        while i >= 0:
            stripped = lines[i].strip()
            if stripped.startswith("///"):
                doc_lines.insert(0, stripped.lstrip("/").strip())
            elif stripped.startswith("#["):
                i -= 1
                continue
            else:
                break
            i -= 1
        return " ".join(doc_lines)[:300]

    @staticmethod
    def _parse_params(raw: str) -> list[str]:
        """Extract parameter names from Rust param string."""
        if not raw:
            return []
        params = []
        for part in raw.split(","):
            part = part.strip()
            if ":" in part:
                name = part.split(":")[0].strip().lstrip("mut ").lstrip("&").lstrip("mut ").strip()
                if name and (name.isidentifier() or name == "self"):
                    params.append(name)
        return params
