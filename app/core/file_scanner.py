
from __future__ import annotations

from pathlib import Path


# Directories that are almost always noise — never contain useful source code
EXCLUDED_DIRS: frozenset[str] = frozenset({
    # Version control
    ".git", ".hg", ".svn",
    # Package managers
    "node_modules", ".pnp",
    # Python
    "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "venv", ".venv", "env", ".env",
    # Build output
    "dist", "build", "out", ".next", ".nuxt", ".output",
    "target",           # Rust / Maven
    "bin", "obj",       # .NET / Java
    # Test coverage / reports
    "coverage", ".nyc_output", "htmlcov",
    # Database migrations (large, rarely useful for context)
    "migrations", "alembic",
    # Static / generated assets
    "static", "staticfiles", "media",
    "public", "assets",
    # Mobile
    ".dart_tool", ".flutter-plugins", ".flutter-plugins-dependencies",
    "Pods",             # iOS CocoaPods
    ".gradle",          # Android
    # IDE / editor
    ".idea", ".vscode",
    # Misc
    "vendor",           # PHP / Go vendored deps
    "third_party",
    ".cache",
})

# Source file extensions we want to index
INDEXABLE_EXTENSIONS: frozenset[str] = frozenset({
    # Python
    ".py",
    # JavaScript / TypeScript
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    # Dart / Flutter
    ".dart",
    # Go
    ".go",
    # Java / Kotlin
    ".java", ".kt", ".kts",
    # Rust
    ".rs",
    # Ruby
    ".rb",
    # PHP
    ".php",
    # C# / F#
    ".cs", ".fs",
    # Swift
    ".swift",
    # C / C++
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp",
})

# Never index these specific filenames even if their extension matches
EXCLUDED_FILENAMES: frozenset[str] = frozenset({
    "setup.py",         # packaging boilerplate
    "conftest.py",      # pytest config
    "manage.py",        # Django entry point (not logic)
})


class FileScanner:
    """
    Scan a repository and return a list of source files to index.

    Improvements over v1:
      - More languages (Go, Rust, Java, Kotlin, Ruby, PHP, C#, Swift, C/C++)
      - Respects .gitignore at the repository root (if present)
      - Larger excluded-dirs list
      - Skips common boilerplate filenames
      - Skips files larger than `max_file_kb` kilobytes
    """

    def __init__(self, max_file_kb: int = 500):
        self.max_file_bytes = max_file_kb * 1024

    def scan(self, repo_path: str) -> list[str]:
        repo    = Path(repo_path)
        ignored = self._load_gitignore(repo)
        files: list[str] = []

        for path in repo.rglob("*"):
            if not path.is_file():
                continue

            # Skip excluded directories anywhere in the path
            if self._in_excluded_dir(path):
                continue

            # Skip gitignored patterns
            if ignored and self._is_gitignored(path, repo, ignored):
                continue

            if path.suffix.lower() not in INDEXABLE_EXTENSIONS:
                continue

            if path.name in EXCLUDED_FILENAMES:
                continue

            # Skip very large files (e.g. auto-generated parsers, vendor blobs)
            try:
                if path.stat().st_size > self.max_file_bytes:
                    continue
            except OSError:
                continue

            files.append(str(path))

        return files

    # ------------------------------------------------------------------ #
    # Gitignore support                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _load_gitignore(repo: Path) -> list[str]:
        gi_path = repo / ".gitignore"
        if not gi_path.exists():
            return []
        try:
            lines = gi_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            patterns = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
            return patterns
        except Exception:
            return []

    @staticmethod
    def _is_gitignored(path: Path, repo: Path, patterns: list[str]) -> bool:
        import fnmatch
        try:
            rel = str(path.relative_to(repo)).replace("\\", "/")
        except ValueError:
            return False
        for pat in patterns:
            # Match against full relative path and just the filename
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(path.name, pat):
                return True
            # Handle directory patterns (e.g. "logs/")
            if pat.endswith("/") and rel.startswith(pat):
                return True
        return False

    @staticmethod
    def _in_excluded_dir(path: Path) -> bool:
        return any(part in EXCLUDED_DIRS for part in path.parts)
