"""Stream a bounded regular input only from the Linux page cache."""

import os
from pathlib import Path
import stat
import sys


RWF_NOWAIT = getattr(os, "RWF_NOWAIT", 0x00000008)  # Linux UAPI, even if the Python headers omit it.


def cached_stream(path, limit, out):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ValueError("Unexpected saved input extent")
        buffer = memoryview(bytearray(1 << 20))
        offset = 0
        while offset < before.st_size:
            try:
                count = os.preadv(fd, [buffer[:before.st_size-offset]], offset, RWF_NOWAIT)
            except OSError as error:
                raise OSError(error.errno, f"{path.name} at byte {offset}: {error.strerror}") from error
            if count <= 0:
                raise OSError("Cache-only input ended early")
            out.write(buffer[:count])
            offset += count
        after = os.stat(path, follow_symlinks=False)
        if ((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)):
            raise OSError("Cache-only input changed")
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        cached_stream(Path(sys.argv[1]), int(sys.argv[2]), sys.stdout.buffer)
    except OSError as error:
        raise SystemExit(f"Cache-only input unavailable ({error})") from error
