"""ttl_dict.py — TtlDict: a dict with time-to-live for each key."""
import time


class TtlDict(dict):
    __slots__ = ("_expires", "_ttl")

    def __init__(self, ttl: int = 86400):
        self._ttl = ttl
        self._expires: dict = {}
        super().__init__()

    def _prune(self, key):
        exp = self._expires.get(key)
        if exp is not None and time.monotonic() > exp:
            del self._expires[key]
            super().pop(key, None)

    def __setitem__(self, key, value):
        self._expires[key] = time.monotonic() + self._ttl
        super().__setitem__(key, value)

    def __getitem__(self, key):
        self._prune(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._prune(key)
        return super().get(key, default)

    def pop(self, key, *args):
        self._prune(key)
        val = super().pop(key, *args)
        self._expires.pop(key, None)
        return val

    def __contains__(self, key):
        self._prune(key)
        return super().__contains__(key)
