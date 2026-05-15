
"""
SerializerLinker
================

Maps Django REST Framework serializers to their backing models.

Detects patterns like:

    class UserSerializer(serializers.ModelSerializer):
        class Meta:
            model = User          ← extracts "User"
            fields = ['id', …]

    class UserSerializer(serializers.Serializer):   ← non-model serializer

Also detects serializer inheritance chains, e.g.:
    class AdminUserSerializer(UserSerializer): …

Output: dict mapping serializer_name → model_name (or None for non-model
serializers).  Also available as a list of enriched dicts for MCP tool output.

Why this matters for token reduction:
  When an AI asks "how is the User model serialized?", Smart-MCP can return
  BOTH the model AND its serializer in a single query, without the AI having
  to first discover the serializer name through a broad search.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Django REST Framework base classes that indicate a serializer
_SERIALIZER_BASES = {
    "ModelSerializer",
    "HyperlinkedModelSerializer",
    "Serializer",
    "BaseSerializer",
    "ListSerializer",
}


class SerializerLinker:
    """
    Parameters
    ----------
    repo_path : str
        Repository root — scanned for all *.py files.
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def extract(self) -> list[dict]:
        """
        Scan the repository and return all serializer → model links.

        Returns a list of dicts:
            {
                "serializer":  "UserSerializer",
                "model":       "User",          # None if no Meta.model
                "file":        "/path/to/serializers.py",
                "line":        12,
                "is_model_serializer": True,
                "fields":      ["id", "username", "email"],
                "inherited_from": [],           # parent serializer names
            }
        """
        results: list[dict] = []
        py_files = list(self.repo_path.rglob("*.py"))

        for py_file in py_files:
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                tree    = ast.parse(content, filename=str(py_file))
                links   = self._parse_file(tree, str(py_file))
                results.extend(links)
            except Exception as exc:
                logger.debug(f"SerializerLinker: skip {py_file}: {exc}")

        logger.info(f"SerializerLinker: found {len(results)} serializer definitions")
        return results

    def as_map(self) -> dict[str, str | None]:
        """Return {serializer_name: model_name} mapping."""
        return {r["serializer"]: r["model"] for r in self.extract()}

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _parse_file(self, tree: ast.AST, file_path: str) -> list[dict]:
        results = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            # Check if any base class looks like a serializer
            base_names    = self._base_names(node)
            is_serializer = bool(base_names & _SERIALIZER_BASES)

            # Check parent serializer names (inheritance chain)
            inherited_from = [b for b in base_names if b.endswith("Serializer")]

            if not (is_serializer or inherited_from):
                continue

            is_model_serializer = bool(
                base_names & {"ModelSerializer", "HyperlinkedModelSerializer"}
            )

            model_name, fields = self._extract_meta(node)

            results.append({
                "serializer":          node.name,
                "model":               model_name,
                "file":                file_path,
                "line":                node.lineno,
                "is_model_serializer": is_model_serializer,
                "fields":              fields,
                "inherited_from":      inherited_from,
            })

        return results

    @staticmethod
    def _base_names(node: ast.ClassDef) -> set[str]:
        """Return the simple names of all base classes."""
        names: set[str] = set()
        for base in node.bases:
            if isinstance(base, ast.Name):
                names.add(base.id)
            elif isinstance(base, ast.Attribute):
                names.add(base.attr)
        return names

    @staticmethod
    def _extract_meta(class_node: ast.ClassDef) -> tuple[str | None, list[str]]:
        """
        Find the inner `class Meta` and extract `model` and `fields`.
        Returns (model_name, fields_list).
        """
        for node in ast.iter_child_nodes(class_node):
            if not isinstance(node, ast.ClassDef) or node.name != "Meta":
                continue

            model_name: str | None = None
            fields: list[str] = []

            for stmt in ast.iter_child_nodes(node):
                if not isinstance(stmt, ast.Assign):
                    continue
                for target in stmt.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if target.id == "model":
                        model_name = SerializerLinker._expr_to_str(stmt.value)
                    elif target.id == "fields":
                        fields = SerializerLinker._list_to_strs(stmt.value)

            return model_name, fields

        return None, []

    @staticmethod
    def _expr_to_str(node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    @staticmethod
    def _list_to_strs(node: ast.expr) -> list[str]:
        if isinstance(node, ast.Constant) and node.value == "__all__":
            return ["__all__"]
        if isinstance(node, (ast.List, ast.Tuple)):
            result = []
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    result.append(elt.value)
            return result
        return []
