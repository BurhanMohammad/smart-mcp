
import ast
from pathlib import Path


class PythonParser:
    """
    Full AST-based Python parser.

    Extracts for every function / async-function / class:
      - name, type, start_line, end_line
      - decorators  (raw strings, e.g. "@login_required", "@app.get('/users')")
      - docstring   (first paragraph only — avoids ballooning token count)
      - parameters  (positional names; skips *self* / *cls*)
      - return annotation (as string)
      - class_name  (for methods — the containing class)
      - base_classes (for class nodes)

    All of this flows into ASTChunker so chunks have rich, searchable text.
    """

    def parse(self, file_path: str) -> dict:
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            return {"symbols": []}
        except Exception:
            return {"symbols": []}

        symbols: list[dict] = []
        self._walk(tree, symbols, class_name="", source_lines=content.splitlines())
        return {"symbols": symbols}

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _walk(
        self,
        tree: ast.AST,
        symbols: list[dict],
        class_name: str,
        source_lines: list[str],
    ) -> None:
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                base_classes = self._bases(node)
                decorators   = self._decorators(node, source_lines)
                docstring    = self._docstring(node)
                symbols.append({
                    "name":         node.name,
                    "type":         "class",
                    "start_line":   node.lineno,
                    "end_line":     getattr(node, "end_lineno", node.lineno),
                    "decorators":   decorators,
                    "docstring":    docstring,
                    "base_classes": base_classes,
                    "parameters":   [],
                    "return_type":  "",
                    "class_name":   class_name,
                })
                # Recurse into class body to pick up methods
                self._walk(node, symbols, class_name=node.name, source_lines=source_lines)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_async    = isinstance(node, ast.AsyncFunctionDef)
                sym_type    = "async_function" if is_async else "function"
                decorators  = self._decorators(node, source_lines)
                docstring   = self._docstring(node)
                parameters  = self._params(node)
                return_type = self._return_annotation(node)

                # Reclassify based on decorators for better tool routing
                if class_name:
                    # property, classmethod, staticmethod …
                    if any("property" in d for d in decorators):
                        sym_type = "property"
                    elif any("classmethod" in d for d in decorators):
                        sym_type = "classmethod"
                    elif any("staticmethod" in d for d in decorators):
                        sym_type = "staticmethod"
                    else:
                        sym_type = "async_method" if is_async else "method"

                # Detect Django/FastAPI/Flask route handlers
                route_url = self._detect_route(decorators)

                calls = self._extract_calls(node)

                symbols.append({
                    "name":         node.name,
                    "type":         sym_type,
                    "start_line":   node.lineno,
                    "end_line":     getattr(node, "end_lineno", node.lineno),
                    "decorators":   decorators,
                    "docstring":    docstring,
                    "parameters":   parameters,
                    "return_type":  return_type,
                    "class_name":   class_name,
                    "base_classes": [],
                    "route_url":    route_url,
                    "calls":        calls,
                })

    # ------------------------------------------------------------------ #

    def _decorators(self, node: ast.AST, source_lines: list[str]) -> list[str]:
        """Return decorator strings as they appear in source (e.g. '@app.get("/users")')."""
        result = []
        for dec in getattr(node, "decorator_list", []):
            line_no = getattr(dec, "lineno", None)
            if line_no and 0 < line_no <= len(source_lines):
                raw = source_lines[line_no - 1].strip()
                result.append(raw if raw.startswith("@") else f"@{raw}")
            else:
                # Fallback: unparse the AST node
                try:
                    result.append("@" + ast.unparse(dec))
                except Exception:
                    pass
        return result

    def _docstring(self, node: ast.AST) -> str:
        """Extract the first docstring from a function/class body."""
        try:
            doc = ast.get_docstring(node, clean=True)
            if doc:
                # Keep only the first paragraph (up to first blank line)
                first_para = doc.split("\n\n")[0].strip()
                return first_para[:400]
        except Exception:
            pass
        return ""

    def _params(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        """Return parameter names, dropping 'self' and 'cls'."""
        skip = {"self", "cls"}
        params: list[str] = []
        args = node.args
        for arg in args.posonlyargs + args.args + args.kwonlyargs:
            if arg.arg not in skip:
                params.append(arg.arg)
        if args.vararg:
            params.append(f"*{args.vararg.arg}")
        if args.kwarg:
            params.append(f"**{args.kwarg.arg}")
        return params

    def _return_annotation(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        if node.returns is None:
            return ""
        try:
            return ast.unparse(node.returns)
        except Exception:
            return ""

    def _bases(self, node: ast.ClassDef) -> list[str]:
        result = []
        for base in node.bases:
            try:
                result.append(ast.unparse(base))
            except Exception:
                pass
        return result

    def _extract_calls(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        """Collect names of all functions/methods called inside this function body."""
        calls: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.add(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.add(child.func.attr)
        # Remove self-call and common builtins
        calls.discard(node.name)
        builtins = {"print", "len", "range", "str", "int", "float", "list",
                    "dict", "set", "tuple", "bool", "type", "isinstance",
                    "hasattr", "getattr", "setattr", "super", "open", "enumerate",
                    "zip", "map", "filter", "sorted", "reversed", "any", "all"}
        return sorted(calls - builtins)

    def _detect_route(self, decorators: list[str]) -> str:
        """
        Attempt to extract a URL pattern from a route decorator, e.g.
            @app.get('/users/{id}')   → '/users/{id}'
            @router.post('/create')   → '/create'
            @api_view(['GET'])        → ''   (DRF; no URL in decorator)
        """
        import re
        for dec in decorators:
            m = re.search(r"""['"](\/[^'"]*)['"']""", dec)
            if m:
                return m.group(1)
        return ""
