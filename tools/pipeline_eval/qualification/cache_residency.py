"""Read-only Linux page-cache observations outside benchmark clocks."""

import errno
import os
import stat
from collections import Counter
from ctypes import CDLL, POINTER, byref, c_int, c_uint64
from pathlib import Path
from time import time_ns

from leo.storage.short_window import ShortWindowReader
from leo.storage.uri import confined_path


def pages(length, page_size):
    return (length + page_size - 1) // page_size


def load_query(path):
    library = CDLL(str(path))
    function = library.leo_cached_pages
    function.argtypes = [c_int, c_uint64, POINTER(c_uint64)]
    function.restype = c_int

    def query(fd, length):
        value = c_uint64()
        error = function(fd, length, byref(value))
        if error:
            raise OSError(error, os.strerror(error))
        return value.value

    return query


def cache_snapshot(members, page_size, query):
    """Observe current page-cache entries from read-only descriptors."""
    counts = Counter()
    errors = Counter()
    started = time_ns()
    for root, filename, length in members:
        counts["members"] += 1
        try:
            path = confined_path(root, root / filename, must_exist=True)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                metadata = os.fstat(fd)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink != 1
                    or metadata.st_size != length
                ):
                    errors["unexpected_member_metadata"] += 1
                    continue
                counts["cached_pages"] += query(fd, length)
                counts["observed_members"] += 1
                counts["observed_file_pages"] += pages(length, page_size)
            finally:
                os.close(fd)
        except OSError as error:
            errors[errno.errorcode.get(error.errno, "unspecified")] += 1
    return dict(
        started_unix_ns=started,
        ended_unix_ns=time_ns(),
        members=counts["members"],
        observed_members=counts["observed_members"],
        cached_pages=counts["cached_pages"] if counts["observed_members"] else None,
        observed_file_pages=counts["observed_file_pages"],
        unavailable=dict(errors),
    )


def manifest_pins(manifests):
    return [{"path": str(path), "sha256": digest} for path, digest in manifests]


def bound_snapshot(store, recording, manifests, page_size, query):
    """Verify the entire launcher inventory against the assigned segment pins."""
    _, _, inventory = store.inventory(recording, verify_windows=False)
    actual = tuple(
        (Path(row["path"]) / "manifest.json", row["manifest_digest"])
        for row in inventory["segments"]
    )
    if actual != manifests:
        raise ValueError("Cache observation recording differs from its assigned sealed manifests")

    members = []
    for path, digest in actual:
        reader = ShortWindowReader(path.parent)
        if reader.manifest_sha256 != digest:
            raise ValueError("Sealed recording manifest changed before cache observation")
        members.extend(
            (reader.path, chunk.payload_relative_path, chunk.compressed_bytes)
            for chunk in reader.manifest.chunks
        )
    return cache_snapshot(members, page_size, query)
