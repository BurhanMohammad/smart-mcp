import re
from pathlib import Path


class FlutterParser:
    def parse(self, file_path):
        content = Path(file_path).read_text(
            encoding="utf-8",
            errors="ignore"
        )

        classes = re.findall(
            r'class\s+(\w+)',
            content
        )

        symbols = []

        for item in classes:
            symbols.append({
                "name": item,
                "type": "class"
            })

        return {
            "symbols": symbols
        }
