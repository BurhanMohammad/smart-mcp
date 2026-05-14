from pathlib import Path


EXCLUDED_DIRS = {
    "static",
    "node_modules",
    ".git",
    "dist",
    "build",
    "coverage",
    "migrations",
    "__pycache__",
    ".next",
    ".dart_tool",
}


class FileScanner:
    def scan(self, repo_path):
        files = []

        for path in Path(repo_path).rglob("*"):
            if not path.is_file():
                continue

            if any(
                excluded in str(path)
                for excluded in EXCLUDED_DIRS
            ):
                continue

            if path.suffix.lower() in {
                ".py",
                ".ts",
                ".tsx",
                ".js",
                ".jsx",
                ".dart",
            }:
                files.append(str(path))

        return files
