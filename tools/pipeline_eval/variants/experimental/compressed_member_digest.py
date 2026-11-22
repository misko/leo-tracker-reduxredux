"""Hash compressed I/Q while each read is still in the processor cache."""

from contextlib import contextmanager
from hashlib import sha256
from unittest.mock import patch

from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader
from leo.storage.uri import confined_path

from .receiver_ingress import read_regular


@contextmanager
def tiled_member_digest():
    original = ShortWindowReader._member

    def member(reader, name, size, expected):
        if not name.endswith(".zst"):
            return original(reader, name, size, expected)
        path = confined_path(reader.path, reader.path / name, must_exist=True)
        digest = sha256()
        data = read_regular(path, size, hash_block=digest.update)
        if len(data) != size or "sha256:" + digest.hexdigest() != expected:
            raise BundleCorruptionError(f"short-window member changed: {name}")
        return data

    with patch.object(ShortWindowReader, "_member", member):
        yield
