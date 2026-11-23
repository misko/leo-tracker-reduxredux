"""Read one private, signed compressed member into an owned aligned buffer."""

import ctypes as ct
from errno import EINVAL, ENOSYS, ENOTTY, EOPNOTSUPP
from math import lcm
import mmap
import os
import stat
from struct import unpack_from

from leo.storage.errors import BundleCorruptionError


AT_EMPTY_PATH = 0x1000
STATX_DIOALIGN = 0x2000
STATX_DIO_READ_ALIGN = 0x20000
UNSUPPORTED = {EINVAL, ENOSYS, ENOTTY, EOPNOTSUPP}
LIBC = ct.CDLL(None, use_errno=True)


class DirectUnavailable(Exception):
    """The released buffered path should handle this input."""


def direct_alignment(fd):
    function = getattr(LIBC, "statx", None)
    if function is None:
        raise DirectUnavailable
    function.argtypes = (ct.c_int, ct.c_char_p, ct.c_int, ct.c_uint, ct.c_void_p)
    function.restype = ct.c_int
    result = ct.create_string_buffer(256)
    if function(fd, b"", AT_EMPTY_PATH, STATX_DIOALIGN | STATX_DIO_READ_ALIGN, result):
        code = ct.get_errno()
        if code in UNSUPPORTED:
            raise DirectUnavailable
        raise OSError(code, os.strerror(code))
    mask, = unpack_from("=I", result, 0)
    memory, offset = unpack_from("=II", result, 0x98)
    if mask & STATX_DIO_READ_ALIGN:
        read_offset, = unpack_from("=I", result, 0xb4)
        offset = read_offset or offset
    if not mask & STATX_DIOALIGN or min(memory, offset) == 0 or lcm(memory, offset) > 1 << 20:
        raise DirectUnavailable
    return memory, offset


def fingerprint(info):
    return info.st_dev, info.st_ino, info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def read_direct(path, maximum_bytes, stats, *, alignment=direct_alignment, read=os.preadv):
    flags = getattr(os, "O_DIRECT", 0)
    if not flags:
        raise DirectUnavailable
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | flags)
    except OSError as error:
        if error.errno in UNSUPPORTED:
            raise DirectUnavailable from error
        raise
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise BundleCorruptionError("scanner IQ bundle member is not one regular file")
        if before.st_size > maximum_bytes:
            raise BundleCorruptionError("scanner IQ bundle member exceeds its declared bound")
        if before.st_size == 0:
            raise DirectUnavailable
        memory, offset = alignment(fd)
        quantum = lcm(memory, offset)
        rounded = ((before.st_size + quantum - 1) // quantum) * quantum
        owner = mmap.mmap(-1, rounded + memory - 1, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
        address = ct.addressof(ct.c_char.from_buffer(owner))
        start = (-address) % memory
        completed = 0
        read_calls = 0
        with memoryview(owner)[start:start + rounded] as view:
            while completed < before.st_size:
                try:
                    count = read(fd, [view[completed:]], completed)
                except OSError as error:
                    if error.errno in UNSUPPORTED and fingerprint(before) == fingerprint(os.fstat(fd)):
                        raise DirectUnavailable from error
                    raise
                read_calls += 1
                if not count:
                    raise BundleCorruptionError("scanner IQ bundle member ended while reading")
                completed += count
                if completed > before.st_size:
                    raise BundleCorruptionError("scanner IQ bundle member changed while reading")
                if completed < before.st_size and completed % quantum:
                    if fingerprint(before) != fingerprint(os.fstat(fd)):
                        raise BundleCorruptionError("scanner IQ bundle member changed while reading")
                    raise DirectUnavailable
            if fingerprint(before) != fingerprint(os.fstat(fd)):
                raise BundleCorruptionError("scanner IQ bundle member changed while reading")
            stats.update(memory_align=memory, offset_align=offset, rounded_bytes=rounded,
                         accepted_bytes=completed, calls=read_calls)
            return view[:completed].toreadonly()
    finally:
        os.close(fd)


def direct_or_buffered(path, size, stock, stats, *, direct=read_direct):
    try:
        return direct(path, size, stats)
    except DirectUnavailable:
        stats["fallbacks"] = stats.get("fallbacks", 0) + 1
        return stock(path, size)
