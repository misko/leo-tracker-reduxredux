"""Bind the optional SHA-NI experiment without changing SHA-256 digests."""

from contextlib import contextmanager
from ctypes import CDLL, c_int, c_size_t, c_void_p, create_string_buffer
from functools import cache
from hashlib import sha256
from types import FunctionType, SimpleNamespace
from unittest.mock import patch

import numpy as np

from leo.storage.short_window import ShortWindowReader


@cache
def _library(path):
    try:
        lib = CDLL(str(path))
        lib.leo_paired_sha256_supported.argtypes = []
        lib.leo_paired_sha256_supported.restype = c_int
        if not lib.leo_paired_sha256_supported():
            return None
        lib.leo_paired_sha256_context_size.argtypes = []
        lib.leo_paired_sha256_context_size.restype = c_size_t
        lib.leo_paired_sha256_init.argtypes = [c_void_p]
        lib.leo_paired_sha256_init.restype = c_int
        lib.leo_paired_sha256_window.argtypes = [c_void_p, c_void_p, c_size_t, c_void_p]
        lib.leo_paired_sha256_window.restype = c_int
        lib.leo_paired_sha256_digest.argtypes = [c_void_p, c_void_p]
        lib.leo_paired_sha256_digest.restype = c_int
        return lib
    except (OSError, AttributeError):
        return None


class PairedSha256:
    """Return each window digest and accumulate the unpadded chunk digest."""

    def __init__(self, path=None):
        self._lib = _library(path) if path is not None else None
        if self.hardware:
            self._state = create_string_buffer(self._lib.leo_paired_sha256_context_size())
            self._output = create_string_buffer(32)
            if not self._lib.leo_paired_sha256_init(self._state):
                raise RuntimeError("Could not initialize the paired SHA-256 context")
        else:
            self._fallback = sha256()

    @property
    def hardware(self):
        return self._lib is not None

    def window(self, raw):
        if not self.hardware:
            digest = sha256(raw).digest()
            self._fallback.update(raw)
            return digest
        if isinstance(raw, bytes):
            address, size = raw, len(raw)
        else:
            buffer = np.frombuffer(raw, dtype=np.uint8)
            address, size = buffer.ctypes.data, buffer.nbytes
        if not self._lib.leo_paired_sha256_window(self._state, address, size, self._output):
            raise RuntimeError("Could not compute the paired SHA-256 digests")
        return self._output.raw

    def digest(self):
        if not self.hardware:
            return self._fallback.digest()
        if not self._lib.leo_paired_sha256_digest(self._state, self._output):
            raise RuntimeError("Could not finalize the chunk SHA-256 digest")
        return self._output.raw


class _DecodedDigests:
    def __init__(self, library):
        self.library = library
        self.pending = None

    def new_chunk(self):
        if self.pending is not None:
            raise RuntimeError("Previous window verification is incomplete")
        self.chunk = PairedSha256(self.library)
        return self

    def window_digest(self, raw):
        if self.pending is not None:
            raise RuntimeError("Previous window verification is incomplete")
        digest = self.chunk.window(raw)
        self.pending = raw
        return "sha256:" + digest.hex()

    def update(self, raw):
        # The release first checks the standalone digest, then appends the
        # very same bytes to the chunk. An unexpected call order fails closed.
        if raw is not self.pending:
            raise RuntimeError("Decoded chunk update differs from its verified window")
        self.pending = None

    def hexdigest(self):
        if self.pending is not None:
            raise RuntimeError("Previous window verification is incomplete")
        return self.chunk.digest().hex()


def paired_windows(reader, library, *, original=None, **scope):
    """Run the frozen release reader with private decoded-digest bindings."""
    if original is None:
        original = ShortWindowReader.windows
    if library is None or not _library(library) or type(reader) is not ShortWindowReader:
        return original(reader, **scope)
    digests = _DecodedDigests(library)
    globals_ = original.__globals__ | {
        "hashlib": SimpleNamespace(sha256=digests.new_chunk),
        "sha256_digest": digests.window_digest,
    }
    # Function-local bindings keep other readers and the release still using
    # their own manifest, index and compressed-member SHA-256 implementations.
    bound = FunctionType(original.__code__, globals_, argdefs=original.__defaults__)
    bound.__kwdefaults__ = original.__kwdefaults__
    return bound(reader, **scope)


@contextmanager
def paired_decoded_hashes(library):
    """Use paired digests only inside the serial acquisition experiment."""
    if _library(library) is None:
        yield
        return
    release = ShortWindowReader.windows

    def windows(reader, **scope):
        return paired_windows(reader, library, original=release, **scope)

    with patch.object(ShortWindowReader, "windows", windows):
        yield
