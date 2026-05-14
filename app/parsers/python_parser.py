import ast
from pathlib import Path


class PythonParser:
    def parse(self, file_path):
        content = Path(file_path).read_text(
            encoding="utf-8",
            errors="ignore"
        )

        tree = ast.parse(content)

        symbols = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                symbols.append({
                    "name": node.name,
                    "type": "function",
                    "start_line": node.lineno,
                    "end_line": getattr(
                        node,
                        "end_lineno",
                        node.lineno
                    )
                })

            if isinstance(node, ast.AsyncFunctionDef):
                symbols.append({
                    "name": node.name,
                    "type": "async_function",
                    "start_line": node.lineno,
                    "end_line": getattr(
                        node,
                        "end_lineno",
                        node.lineno
                    )
                })

            if isinstance(node, ast.ClassDef):
                symbols.append({
                    "name": node.name,
                    "type": "class",
                    "start_line": node.lineno,
                    "end_line": getattr(
                        node,
                        "end_lineno",
                        node.lineno
                    )
                })

        return {
            "symbols": symbols
        }
