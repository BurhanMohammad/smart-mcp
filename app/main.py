import uuid
import logging

from app.core.file_scanner import FileScanner
from app.core.framework_detector import FrameworkDetector
from app.core.hybrid_retriever import HybridRetriever
from app.chunking.ast_chunker import ASTChunker

from app.parsers.python_parser import PythonParser
from app.parsers.typescript_parser import TypeScriptParser
from app.parsers.flutter_parser import FlutterParser

from app.mcp.tools import register_retriever


class SmartMCP:
    def __init__(self, repo_path):
        self.repo_path = repo_path

        self.detector = FrameworkDetector()
        self.scanner = FileScanner()

        self.python_parser = PythonParser()
        self.typescript_parser = TypeScriptParser()
        self.flutter_parser = FlutterParser()

        self.chunker = ASTChunker()

    def parse_file(self, file):
        if file.endswith(".py"):
            return self.python_parser.parse(file)

        if file.endswith(
            (
                ".ts",
                ".tsx",
                ".js",
                ".jsx"
            )
        ):
            return self.typescript_parser.parse(file)

        if file.endswith(".dart"):
            return self.flutter_parser.parse(file)

        return {
            "symbols": []
        }

    def build_index(self):
        framework = self.detector.detect(
            self.repo_path
        )

        logging.info(f"Detected: {framework}")

        files = self.scanner.scan(
            self.repo_path
        )

        chunks = []

        for file in files:
            try:
                parsed = self.parse_file(file)

                symbols = parsed.get(
                    "symbols",
                    []
                )

                for symbol in symbols:
                    symbol["id"] = str(uuid.uuid4())

                file_chunks = self.chunker.chunk(
                    file,
                    symbols
                )

                chunks.extend(file_chunks)

            except Exception as e:
                logging.warning(f"Failed: {file} -> {e}")

        retriever = HybridRetriever(
            chunks
        )

        register_retriever(retriever)

        logging.info(f"Indexed {len(chunks)} chunks")


if __name__ == "__main__":
    path = input(
        "Repository path: "
    )

    app = SmartMCP(path)

    app.build_index()
