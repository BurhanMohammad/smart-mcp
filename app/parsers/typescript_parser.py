import re
from pathlib import Path


class TypeScriptParser:
    def parse(self, file_path):
        content = Path(file_path).read_text(
            encoding="utf-8",
            errors="ignore"
        )

        symbols = []

        function_matches = re.finditer(
            r'function\s+(\w+)\s*\(',
            content
        )

        class_matches = re.finditer(
            r'class\s+(\w+)',
            content
        )

        for item in function_matches:
            symbols.append({
                "name": item.group(1),
                "type": "function",
            })

        for item in class_matches:
            symbols.append({
                "name": item.group(1),
                "type": "class",
            })

        return {
            "symbols": symbols
        }
