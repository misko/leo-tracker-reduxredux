"""Overlap one sealed compressed member's read with serial receiver work."""

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath
from threading import get_ident
from time import perf_counter_ns, thread_time_ns
from unittest.mock import patch

from leo.storage.errors import BundleCorruptionError
from leo.storage.fast_scan import FastSegmentSource
from leo.storage.pinned import PinnedLocalRoot
from leo.storage.scanner import ScannerIqStore

from .receiver_ingress import read_regular_descriptor
from .receiver_member_lookahead import following_members

MAX_PREFETCH_BYTES = 128 * 1024**2


@dataclass
class MemberPrefetchStats:
    submitted: int = 0
    submitted_bytes: int = 0
    hits: int = 0
    hit_bytes: int = 0
    fallback: int = 0
    demand_wait_ns: int = 0
    worker_cpu_ns: int = 0


def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def prefetch_member(root, name, size, stats):
    """Read bounded bytes on an anchored descriptor, leaving all hashes to the reader."""
    start = thread_time_ns()
    member = PurePosixPath(name)
    try:
        with ExitStack() as stack:
            directory = stack.enter_context(closing(PinnedLocalRoot(root)))
            if member.parent.parts:
                directory = stack.enter_context(closing(directory.child(*member.parent.parts)))
            fd = os.open(member.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory.fileno())
            stack.callback(os.close, fd)
            identity = file_identity(os.fstat(fd))
            payload = read_regular_descriptor(fd, size)
            if len(payload) == size and file_identity(os.fstat(fd)) == identity:
                return payload, identity
    except (OSError, ValueError, BundleCorruptionError):
        # Speculative failures belong to the verified reader at normal demand.
        return None
    finally:
        stats.worker_cpu_ns += thread_time_ns() - start
    return None


@contextmanager
def compressed_member_prefetch():
    """Supply at most one read-only buffer to the original verified member path."""
    stats = MemberPrefetchStats()
    caller = get_ident()
    original_windows = FastSegmentSource.windows
    original_read = ScannerIqStore._read_regular
    pending = None

    def read(path, maximum_bytes):
        nonlocal pending
        if get_ident() == caller and pending is not None and pending[:2] == (path, maximum_bytes):
            _, _, future = pending
            pending = None
            start = perf_counter_ns()
            ready = future.result()
            stats.demand_wait_ns += perf_counter_ns() - start
            if ready is not None:
                payload, identity = ready
                try:
                    if file_identity(os.stat(path, follow_symlinks=False)) == identity:
                        stats.hits += 1
                        stats.hit_bytes += len(payload)
                        return payload
                except OSError:
                    pass
            stats.fallback += 1
        return original_read(path, maximum_bytes)

    def discard():
        nonlocal pending
        if pending is not None:
            pending[2].cancel()
            pending = None

    def windows(source):
        nonlocal pending
        if get_ident() != caller:
            yield from original_windows(source)
            return
        following = following_members(source)
        root = source.reader.path
        try:
            with closing(original_windows(source)) as released:
                for window in released:
                    chunk = following.get(window.sequence)
                    if pending is None and chunk is not None and 0 < chunk.compressed_bytes <= MAX_PREFETCH_BYTES:
                        name, size = chunk.payload_relative_path, chunk.compressed_bytes
                        pending = (root / name, size, pool.submit(prefetch_member, root, name, size, stats))
                        stats.submitted += 1
                        stats.submitted_bytes += size
                    yield window
        finally:
            discard()

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="algo08-read") as pool:
        with (patch.object(FastSegmentSource, "windows", windows),
              patch.object(ScannerIqStore, "_read_regular", staticmethod(read))):
            try:
                yield stats
            finally:
                discard()
