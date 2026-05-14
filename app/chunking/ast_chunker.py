class ASTChunker:
    def chunk(self, file, symbols):
        chunks = []

        for symbol in symbols:
            chunks.append({
                "id": symbol["id"],
                "symbol": symbol["name"],
                "file": file,
                "type": symbol["type"],
                "start_line": symbol.get(
                    "start_line",
                    0
                ),
                "end_line": symbol.get(
                    "end_line",
                    0
                ),
                "text": (
                    f'{symbol["name"]} '
                    f'{symbol["type"]} '
                    f'{file}'
                )
            })

        return chunks
