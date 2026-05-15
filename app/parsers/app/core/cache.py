from functools import lru_cache


class Cache:
    @lru_cache(maxsize=1024)
    def get(self, key):
        return key