from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SUPPORTED_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".dart",
}

IGNORE_DIRS = {
    ".git",
    "node_modules",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".next",
    ".idea",
}