import hashlib
from pathlib import Path


class IndexTracker:
    def file_hash(self, file_path: str):
        content = Path(file_path).read_bytes()

        return hashlib.sha256(content).hexdigest()