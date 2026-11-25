"""Condition only missing pages of the admitted private DS30-0016 copy."""

import argparse
import ctypes
import json
import os
import resource
from contextlib import ExitStack, contextmanager
from pathlib import Path
from time import monotonic, process_time

CAP = 8 * 1024 * 1024
PAGE = os.sysconf("SC_PAGE_SIZE")
LIB = ctypes.CDLL(None, use_errno=True)
LIB.mmap.argtypes = (
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_longlong,
)
LIB.mmap.restype = ctypes.c_void_p
LIB.mincore.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_ubyte))
LIB.madvise.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int)
LIB.munmap.argtypes = (ctypes.c_void_p, ctypes.c_size_t)


def checked_zero(code):
    if code != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))


@contextmanager
def read_only_map(path):
    import mmap

    with path.open("rb", buffering=0) as stream:
        length = os.fstat(stream.fileno()).st_size
        address = LIB.mmap(None, length, mmap.PROT_READ, mmap.MAP_SHARED, stream.fileno(), 0)
        if address is None or address == ctypes.c_void_p(-1).value:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))
        try:
            os.posix_fadvise(stream.fileno(), 0, 0, os.POSIX_FADV_RANDOM)
            checked_zero(LIB.madvise(address, length, mmap.MADV_RANDOM))
            yield address, length
        finally:
            checked_zero(LIB.munmap(address, length))


def missing(address, length):
    statuses = (ctypes.c_ubyte * ((length + PAGE - 1) // PAGE))()
    checked_zero(LIB.mincore(address, length, statuses))
    return [index for index, status in enumerate(statuses) if not status & 1]


def condition(staged, paths):
    if (
        staged.parent != Path("/dev/shm/leo-v3-guarded-selective-0016-stage01")
        or staged != staged.resolve(strict=True)
        or not paths
    ):
        raise ValueError("Expected the already staged DS30-0016 original")
    if any(
        not path.is_relative_to(staged)
        or path != path.resolve(strict=True)
        or not path.name.endswith(".ci16.zst")
        or path.stat().st_dev != staged.stat().st_dev
        for path in paths
    ):
        raise ValueError("Only admitted existing compressed originals can be conditioned")
    t = monotonic(), process_time(), resource.getrusage(resource.RUSAGE_SELF)
    completed = []
    with ExitStack() as stack:
        maps = [(path, *stack.enter_context(read_only_map(path))) for path in paths]
        scans = [
            (path, address, length, missing(address, length)) for path, address, length in maps
        ]
        planned = sum(len(pages) for _, _, _, pages in scans) * PAGE
        if planned > CAP:
            raise ValueError(f"Missing original pages exceed the {CAP}-byte conditioning cap")
        for path, address, length, pages in scans:
            touched = 0
            for index in pages:
                offset = index * PAGE
                if missing(address + offset, min(PAGE, length - offset)):
                    _ = ctypes.c_ubyte.from_address(address + offset).value
                    touched += 1
            completed.append(
                dict(
                    path=str(path),
                    pages_planned=len(pages),
                    pages_touched=touched,
                    pages_missing_after=len(missing(address, length)),
                )
            )
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return dict(
        files=completed,
        page_bytes=PAGE,
        limit_bytes=CAP,
        planned_address_bytes=planned,
        wall_s=monotonic() - t[0],
        cpu_s=process_time() - t[1],
        major_faults=usage.ru_majflt - t[2].ru_majflt,
        minor_faults=usage.ru_minflt - t[2].ru_minflt,
        input_blocks=usage.ru_inblock - t[2].ru_inblock,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staged", type=Path)
    parser.add_argument("paths", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps(condition(args.staged, args.paths), allow_nan=False))
