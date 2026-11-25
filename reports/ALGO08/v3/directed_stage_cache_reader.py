"""Fail-closed local byte port for the ordinary signed short-window reader."""

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from resource import RUSAGE_THREAD, getrusage
from stat import S_ISREG
from unittest.mock import patch


RWF_NOWAIT = getattr(os, "RWF_NOWAIT", 0x8)
BLOCK = 1024 * 1024


class CacheSourceUnavailable(OSError):
    """The exact detached source cannot be read without a blocking fallback."""


@dataclass(frozen=True)
class Extent:
    size: int
    sha256: str
    kind: str


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mode, info.st_nlink, info.st_mtime_ns, info.st_ctime_ns)


def thread_input_blocks():
    return getrusage(RUSAGE_THREAD).ru_inblock


class CacheReader:
    def __init__(self, directory, extents):
        self.directory = directory
        self.extents = dict(extents)
        self.metadata = {}
        self.fingerprints = {}
        self.read_files = set()
        self.bytes = 0
        self.returned_bytes = 0
        self.requests = 0
        self.metadata_hits = 0
        self.dir_fd = None
        self.opening = None

    def __enter__(self):
        if self.directory.resolve(strict=True) != self.directory:
            raise CacheSourceUnavailable("The detached prefix must be a direct directory")
        self.dir_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        if identity(os.fstat(self.dir_fd)) != identity(self.directory.lstat()):
            self.__exit__(None, None, None)
            raise CacheSourceUnavailable("The detached directory changed before use")
        return self

    def __exit__(self, *_):
        os.close(self.dir_fd)
        self.dir_fd = None

    def read(self, path, maximum):
        if self.dir_fd is None or path.parent != self.directory or path.name not in self.extents:
            raise CacheSourceUnavailable("Waveform read escaped the sealed detached file list")
        extent = self.extents[path.name]
        if not 0 < extent.size <= maximum:
            raise CacheSourceUnavailable(f"The enrolled extent exceeds the ordinary reader bound: {path.name}")
        if path.name in self.metadata:
            if identity(os.stat(path.name,dir_fd=self.dir_fd,follow_symlinks=False)) != self.fingerprints[path.name]:
                raise CacheSourceUnavailable(f"Cached signed metadata changed: {path.name}")
            self.metadata_hits += 1
            return self.metadata[path.name]
        if path.name in self.read_files:
            raise CacheSourceUnavailable("A compressed member would be read twice")

        self.opening = path.name
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=self.dir_fd)
        finally:
            self.opening = None
        try:
            first = os.fstat(fd)
            if not S_ISREG(first.st_mode) or first.st_nlink != 1 or first.st_size != extent.size:
                raise CacheSourceUnavailable(f"The booked regular-file extent changed: {path.name}")
            body = bytearray(extent.size)
            view = memoryview(body)
            for offset in range(0, extent.size, BLOCK):
                target = view[offset:offset + BLOCK]
                blocks = thread_input_blocks()
                self.requests += 1
                try:
                    received = os.preadv(fd, [target], offset, RWF_NOWAIT)
                except OSError as error:
                    raise CacheSourceUnavailable(
                        f"Cache-only read failed for {path.name} at byte {offset}: {error.strerror}"
                    ) from error
                self.returned_bytes += received
                if received != len(target) or thread_input_blocks() != blocks:
                    raise CacheSourceUnavailable(f"Short or physical cache-only read: {path.name} at byte {offset}")
                self.bytes += received
            if (identity(first) != identity(os.fstat(fd))
                    or identity(first) != identity(os.stat(path.name, dir_fd=self.dir_fd, follow_symlinks=False))
                    or identity(os.fstat(self.dir_fd)) != identity(self.directory.lstat())):
                raise CacheSourceUnavailable(f"The detached source changed while reading: {path.name}")
            if "sha256:" + sha256(body).hexdigest() != extent.sha256:
                raise CacheSourceUnavailable(f"The detached source differs from the signed enrollment: {path.name}")
        finally:
            os.close(fd)
        self.read_files.add(path.name)
        self.fingerprints[path.name] = identity(first)
        if extent.kind in {"manifest", "index"}:
            self.metadata[path.name] = bytes(body)
            return self.metadata[path.name]
        return body

    def receipt(self):
        return dict(files=sorted(self.read_files), bytes=self.bytes, nowait_requests=self.requests,
                    returned_bytes=self.returned_bytes, metadata_reuses=self.metadata_hits, persistent_copy_bytes=0)

    def verify_complete(self):
        if (self.read_files != self.extents.keys()
                or identity(os.fstat(self.dir_fd)) != identity(self.directory.lstat())
                or any(identity(os.stat(name,dir_fd=self.dir_fd,follow_symlinks=False)) != expected
                       for name,expected in self.fingerprints.items())):
            raise CacheSourceUnavailable("The detached prefix is incomplete or changed during replay")


@contextmanager
def signed_windows(reader):
    """Replace only the regular byte read. All ordinary decoding and checks remain installed."""
    from leo.storage.scanner import ScannerIqStore

    with reader, patch.object(ScannerIqStore, "_read_regular", staticmethod(reader.read)):
        yield reader


def ordered_hashes(directory, manifest_pin, *, members=6, windows_per_member=64):
    """Read signed index hashes before the sweep, with no encoded member read."""
    from leo.storage.short_window import ShortWindowIndexV2, ShortWindowReader

    stock = ShortWindowReader(directory)
    manifest = stock.manifest
    chunks = manifest.chunks[:members]
    if (stock.manifest_sha256 != manifest_pin or manifest.schema_version != 2
            or manifest.sample_rate_hz != 10_000_000 or tuple(manifest.receiver_ids) != (0, 1)
            or len(chunks) != members):
        raise CacheSourceUnavailable("The original signed stereo manifest or first-member scope changed")
    hashes = []
    for number, chunk in enumerate(chunks):
        if (chunk.chunk_index, chunk.first_sequence, chunk.window_count) != (
            number, number * windows_per_member, windows_per_member
        ):
            raise CacheSourceUnavailable("The replay requires the first complete consecutive original members")
        index = stock._member(chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256)
        for line in index.splitlines():
            row = ShortWindowIndexV2.model_validate_json(line)
            if row.sequence != len(hashes):
                raise CacheSourceUnavailable("The ordered signed index changed")
            hashes.append(row.iq_sha256)
        if len(hashes) != (number + 1) * windows_per_member:
            raise CacheSourceUnavailable("The signed index does not cover the complete member")
    return hashes
