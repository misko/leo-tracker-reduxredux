"""Reuse the original verified PNG read within one fresh publication."""

from contextlib import contextmanager
from unittest.mock import patch


class VerifiedPngReads:
    def __init__(self, root, decode, audit):
        if root.exists() or not root.parent.is_dir():
            raise ValueError("Verified image read reuse requires a fresh publication directory")
        self.root = root.resolve()
        self.decode = decode
        self.audit = audit
        self.images = {}
        audit.update(verified=0, reused=0, fallbacks=0, verified_bytes=0)

    @contextmanager
    def capture(self, storage):
        original = storage.artifact

        def artifact(store, run, name, expected=None):
            image = original(store, run, name, expected)
            key = (run, name, expected)
            if store.root == self.root and isinstance(expected, str) and key not in self.images:
                self.images[key] = self.decode(image, expected)
                self.audit["verified"] += 1
                self.audit["verified_bytes"] += len(image)
            return image

        with patch.object(storage, "artifact", artifact):
            yield

    def read(self, store, run, name, expected):
        key = (run, name, expected)
        if store.root == self.root and key in self.images:
            self.audit["reused"] += 1
            return self.images.pop(key)
        self.audit["fallbacks"] += 1
        return self.decode(store.artifact(run, name, expected), expected)
