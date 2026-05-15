from pathlib import Path


class ContextSelector:
    def get_context(self, query: str, symbol_index: list):
        relevant = []

        query = query.lower()

        for symbol in symbol_index:
            if query in symbol["name"].lower():
                relevant.append(symbol)

        return relevant

    def load_code(self, file_path: str, max_lines: int = 200):
        content = Path(file_path).read_text(encoding="utf-8")

        lines = content.splitlines()

        return "\n".join(lines[:max_lines])