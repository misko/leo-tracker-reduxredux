"""Sample Linux page-cache residency of a running numerical worker's unlinked scratch."""

import argparse
import ctypes
import json
import mmap
import os
from pathlib import Path
from time import perf_counter, sleep

MINCORE = ctypes.CDLL(None, use_errno=True).mincore
MINCORE.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
MINCORE.restype = ctypes.c_int


def resident(fd, size):
    pages = (size + mmap.PAGESIZE - 1) // mmap.PAGESIZE
    result = (ctypes.c_ubyte * pages)()
    with mmap.mmap(fd, size, access=mmap.ACCESS_COPY) as mapped:
        view = ctypes.c_ubyte.from_buffer(mapped)
        status = MINCORE(ctypes.addressof(view), size, ctypes.addressof(result))
        del view
        if status != 0:
            raise OSError(ctypes.get_errno(), "mincore")
    return sum(bool(page & 1) for page in result) * mmap.PAGESIZE


def sample(pid, scratch):
    process = Path(f"/proc/{pid}")
    status = {
        name: int(value.split()[0])
        for name, value in (
            line.split(":", 1) for line in (process / "status").read_text().splitlines()
        )
        if name in ("VmRSS", "VmHWM")
    }
    io = {
        name: int(value)
        for name, value in (
            line.split(":", 1) for line in (process / "io").read_text().splitlines()
        )
        if name in ("rchar", "wchar", "read_bytes", "write_bytes")
    }
    files = []
    for path in (process / "fd").iterdir():
        target = os.readlink(path)
        if not target.endswith(" (deleted)") or Path(target).parent != scratch:
            continue
        with path.open("rb") as f:
            size = os.fstat(f.fileno()).st_size
            if size:
                files.append((size, resident(f.fileno(), size)))
    return dict(
        process_rss_kib=status["VmRSS"],
        process_peak_rss_kib=status["VmHWM"],
        files=len(files),
        scratch_bytes=sum(n for n, _ in files),
        resident_scratch_bytes=sum(n for _, n in files),
        io=io,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pid", type=int)
    p.add_argument("scratch", type=Path)
    p.add_argument("--seconds", type=float, default=60)
    args = p.parse_args()
    start = perf_counter()
    while perf_counter() - start < args.seconds:
        try:
            result = sample(args.pid, args.scratch.resolve())
        except (FileNotFoundError, ProcessLookupError):
            break
        print(json.dumps(dict(elapsed_s=perf_counter() - start, **result)), flush=True)
        sleep(5)


if __name__ == "__main__":
    main()
