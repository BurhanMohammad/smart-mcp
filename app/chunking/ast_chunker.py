
from pathlib import Path
from app.core.code_extractor import CodeExtractor

_extractor = CodeExtractor()


class ASTChunker:
    """
    Turns parsed symbols into indexable chunks that carry *real source code*.

    Previously, chunk["text"] was just "symbol_name type file" which made
    embeddings nearly useless.  Now every chunk's text field is built from:

        1.  symbol name + type  (keyword-search anchor)
        2.  file path           (path-based queries: "in views.py")
        3.  class context       (e.g. "inside class UserSerializer")
        4.  decorators          (e.g. "@login_required", "@app.get('/users')")
        5.  docstring           (first 200 chars)
        6.  actual source code  (up to max_code_lines)

    This dramatically improves both BM25 keyword matching and FAISS embedding
    quality.
    """

    def __init__(self, max_code_lines: int = 80):
        self.max_code_lines = max_code_lines

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def chunk(self, file_path: str, symbols: list[dict]) -> list[dict]:
        chunks = []

        for symbol in symbols:
            chunk = self._build_chunk(file_path, symbol)
            if chunk:
                chunks.append(chunk)

        return chunks

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _build_chunk(self, file_path: str, symbol: dict) -> dict | None:
        name        = symbol.get("name", "")
        sym_type    = symbol.get("type", "unknown")
        start_line  = symbol.get("start_line", 1)
        end_line    = symbol.get("end_line", start_line)
        docstring   = symbol.get("docstring", "")
        decorators  = symbol.get("decorators", [])
        class_name  = symbol.get("class_name", "")
        parameters  = symbol.get("parameters", [])
        return_type = symbol.get("return_type", "")
        base_classes = symbol.get("base_classes", [])

        if not name:
            return None

        # --- Actual code (the KEY improvement) ---
        code = _extractor.extract(
            file_path, start_line, end_line, self.max_code_lines
        )

        # --- Relative file path for cleaner embedding text ---
        rel_file = file_path
        try:
            from pathlib import Path as _P
            rel_file = str(_P(file_path).name)   # just filename; full path in metadata
        except Exception:
            pass

        # --- Build rich text for embedding / BM25 ---
        parts = [f"{sym_type} {name}"]

        if class_name:
            parts.append(f"in class {class_name}")

        parts.append(f"file {rel_file}")

        if base_classes:
            parts.append(f"extends {' '.join(base_classes)}")

        if decorators:
            parts.append("decorators: " + "  ".join(decorators))

        if parameters:
            parts.append("params: " + " ".join(parameters[:10]))

        if return_type:
            parts.append(f"returns {return_type}")

        if docstring:
            parts.append(docstring[:300])

        if code:
            parts.append(code[: 800])     # cap at ~800 chars ≈ 200 tokens

        text = "\n".join(parts)

        return {
            "id":          symbol["id"],
            "symbol":      name,
            "file":        file_path,
            "type":        sym_type,
            "start_line":  start_line,
            "end_line":    end_line,
            "class_name":  class_name,
            "decorators":  decorators,
            "parameters":  parameters,
            "return_type": return_type,
            "base_classes": base_classes,
            "docstring":   docstring,
            "code":        code,
            "calls":       symbol.get("calls", []),
            "text":        text,
        }
