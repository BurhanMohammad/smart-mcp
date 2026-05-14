from pathlib import Path
import hashlib


class IncrementalIndexer:
    def __init__(self):
        self.cache = {}

    def hash_file(self, path):
        try:
            data = Path(path).read_bytes()
            return hashlib.md5(data).hexdigest()
        except Exception:
            return None

    def changed(self, path):
        current = self.hash_file(path)

        if current is None:
            return False

        previous = self.cache.get(path)

        self.cache[path] = current

        return current != previous
