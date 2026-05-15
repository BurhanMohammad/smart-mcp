
"""
RouteMapper
===========

Maps URL routes to view/handler functions for Django, FastAPI, Flask,
Express.js (Node), and Next.js (file-system routing).

This was listed as a Future Improvement in the README and is now implemented.

Usage
-----
    mapper = RouteMapper(repo_path, framework)
    routes = mapper.extract()
    # returns: [{"method": "GET", "path": "/users/", "handler": "list_users",
    #            "file": "...", "line": 12}, ...]
"""

from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class RouteMapper:
    """
    Extract route → handler mappings from a repository.

    Parameters
    ----------
    repo_path : str
        Absolute path to the repository root.
    framework : str
        One of: "django", "fastapi", "flask", "express", "nextjs", "unknown".
        When "unknown", all strategies are attempted.
    """

    def __init__(self, repo_path: str, framework: str = "unknown"):
        self.repo_path = Path(repo_path)
        self.framework = framework.lower()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def extract(self) -> list[dict]:
        """Return all discovered routes as a list of dicts."""
        routes: list[dict] = []

        if self.framework in ("django", "unknown"):
            routes.extend(self._extract_django())

        if self.framework in ("fastapi", "flask", "unknown"):
            routes.extend(self._extract_fastapi_flask())

        if self.framework in ("express", "unknown"):
            routes.extend(self._extract_express())

        if self.framework in ("nextjs", "unknown"):
            routes.extend(self._extract_nextjs())

        # De-duplicate (same path+method combo)
        seen: set[tuple] = set()
        unique: list[dict] = []
        for r in routes:
            key = (r.get("method"), r.get("path"))
            if key not in seen:
                seen.add(key)
                unique.append(r)

        logger.info(f"RouteMapper: found {len(unique)} routes")
        return unique

    # ------------------------------------------------------------------ #
    # Django: urls.py                                                      #
    # ------------------------------------------------------------------ #

    def _extract_django(self) -> list[dict]:
        routes: list[dict] = []
        url_files = list(self.repo_path.rglob("urls.py"))

        for url_file in url_files:
            try:
                content = url_file.read_text(encoding="utf-8", errors="ignore")
                tree    = ast.parse(content, filename=str(url_file))
                routes.extend(self._parse_django_urlconf(tree, str(url_file), content))
            except Exception as exc:
                logger.debug(f"Django URL parse error {url_file}: {exc}")

        return routes

    def _parse_django_urlconf(
        self, tree: ast.AST, file_path: str, content: str
    ) -> list[dict]:
        routes: list[dict] = []
        lines  = content.splitlines()

        for node in ast.walk(tree):
            # path("url/", view_func, name="name")
            # re_path(r"url/", view_func, ...)
            if not isinstance(node, ast.Call):
                continue
            func_name = self._call_name(node)
            if func_name not in {"path", "re_path", "url"}:
                continue

            if len(node.args) < 2:
                continue

            url_arg  = node.args[0]
            view_arg = node.args[1]

            url_str  = self._str_value(url_arg)
            view_str = self._ast_expr_to_str(view_arg)

            if url_str is None:
                continue

            routes.append({
                "method":  "GET/POST",
                "path":    "/" + url_str.lstrip("/"),
                "handler": view_str,
                "file":    file_path,
                "line":    node.lineno,
                "framework": "django",
            })

        return routes

    # ------------------------------------------------------------------ #
    # FastAPI / Flask                                                      #
    # ------------------------------------------------------------------ #

    def _extract_fastapi_flask(self) -> list[dict]:
        routes: list[dict] = []
        py_files = list(self.repo_path.rglob("*.py"))

        # Pattern: @app.get('/path')  or  @router.post('/path')
        pattern = re.compile(
            r"@(?:\w+)\.(?P<method>get|post|put|patch|delete|options|head)\s*"
            r"\(\s*['\"](?P<path>[^'\"]+)['\"]",
            re.IGNORECASE,
        )

        for py_file in py_files:
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                lines   = content.splitlines()

                for m in pattern.finditer(content):
                    line_no  = content[:m.start()].count("\n") + 1
                    # The function definition is usually 1-2 lines after the decorator
                    handler  = self._next_function_name(lines, line_no)
                    routes.append({
                        "method":    m.group("method").upper(),
                        "path":      m.group("path"),
                        "handler":   handler,
                        "file":      str(py_file),
                        "line":      line_no,
                        "framework": "fastapi/flask",
                    })
            except Exception as exc:
                logger.debug(f"FastAPI/Flask route parse error {py_file}: {exc}")

        return routes

    # ------------------------------------------------------------------ #
    # Express.js                                                           #
    # ------------------------------------------------------------------ #

    def _extract_express(self) -> list[dict]:
        routes: list[dict] = []
        js_files = list(self.repo_path.rglob("*.js")) + list(self.repo_path.rglob("*.ts"))

        pattern = re.compile(
            r"(?:app|router|server)\s*\.\s*(?P<method>get|post|put|patch|delete|options|head)\s*"
            r"\(\s*['\"](?P<path>[^'\"]+)['\"]",
            re.IGNORECASE | re.MULTILINE,
        )

        for js_file in js_files:
            if any(p in str(js_file) for p in ("node_modules", "dist", ".next")):
                continue
            try:
                content = js_file.read_text(encoding="utf-8", errors="ignore")
                for m in pattern.finditer(content):
                    line_no = content[:m.start()].count("\n") + 1
                    routes.append({
                        "method":    m.group("method").upper(),
                        "path":      m.group("path"),
                        "handler":   "",
                        "file":      str(js_file),
                        "line":      line_no,
                        "framework": "express",
                    })
            except Exception as exc:
                logger.debug(f"Express route parse error {js_file}: {exc}")

        return routes

    # ------------------------------------------------------------------ #
    # Next.js file-system routing                                          #
    # ------------------------------------------------------------------ #

    def _extract_nextjs(self) -> list[dict]:
        routes: list[dict] = []

        # Next.js 13+ app/ directory
        app_dir = self.repo_path / "app"
        if app_dir.exists():
            for route_file in app_dir.rglob("route.ts"):
                url_path = self._nextjs_file_to_route(route_file, app_dir)
                routes.extend(self._parse_nextjs_route_file(route_file, url_path))
            for page_file in app_dir.rglob("page.tsx"):
                url_path = self._nextjs_file_to_route(page_file, app_dir)
                routes.append({
                    "method":    "GET",
                    "path":      url_path,
                    "handler":   "default",
                    "file":      str(page_file),
                    "line":      1,
                    "framework": "nextjs",
                })

        # Next.js 12 pages/ directory
        pages_dir = self.repo_path / "pages"
        if pages_dir.exists():
            for page_file in pages_dir.rglob("*.tsx"):
                if page_file.name.startswith("_"):
                    continue
                url_path = self._nextjs_file_to_route(page_file, pages_dir)
                routes.append({
                    "method":    "GET",
                    "path":      url_path,
                    "handler":   "default",
                    "file":      str(page_file),
                    "line":      1,
                    "framework": "nextjs",
                })

        return routes

    def _parse_nextjs_route_file(self, file_path: Path, url_path: str) -> list[dict]:
        routes: list[dict] = []
        pattern = re.compile(
            r"export\s+(?:async\s+)?function\s+(?P<method>GET|POST|PUT|PATCH|DELETE|OPTIONS)\s*\(",
            re.MULTILINE,
        )
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for m in pattern.finditer(content):
                line_no = content[:m.start()].count("\n") + 1
                routes.append({
                    "method":    m.group("method"),
                    "path":      url_path,
                    "handler":   m.group("method"),
                    "file":      str(file_path),
                    "line":      line_no,
                    "framework": "nextjs",
                })
        except Exception:
            pass
        return routes

    @staticmethod
    def _nextjs_file_to_route(file_path: Path, root_dir: Path) -> str:
        rel   = file_path.relative_to(root_dir)
        parts = list(rel.parts[:-1])   # drop filename
        # [slug] → :slug
        parts = [f":{p[1:-1]}" if p.startswith("[") and p.endswith("]") else p
                 for p in parts]
        return "/" + "/".join(parts) if parts else "/"

    # ------------------------------------------------------------------ #
    # Utility helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _call_name(node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    @staticmethod
    def _str_value(node: ast.expr) -> Optional[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    @staticmethod
    def _ast_expr_to_str(node: ast.expr) -> str:
        try:
            return ast.unparse(node)
        except Exception:
            return ""

    @staticmethod
    def _next_function_name(lines: list[str], decorator_line: int) -> str:
        for i in range(decorator_line, min(len(lines), decorator_line + 5)):
            m = re.search(r"(?:async\s+)?def\s+(\w+)", lines[i])
            if m:
                return m.group(1)
        return ""
