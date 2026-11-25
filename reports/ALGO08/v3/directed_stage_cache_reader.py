"""Cache admission with measured, fail-closed reads for the signed input."""

from contextlib import contextmanager
import ctypes
from dataclasses import dataclass
import errno
from hashlib import sha256
import mmap
import os
from pathlib import Path
from resource import RUSAGE_THREAD, getrusage
from stat import S_ISREG
from unittest.mock import patch


RWF_NOWAIT = getattr(os, "RWF_NOWAIT", 0x8)
BLOCK = 1024 * 1024
PAGE = os.sysconf("SC_PAGE_SIZE")
LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.mmap.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long)
LIBC.mmap.restype = ctypes.c_void_p
LIBC.mincore.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_ubyte))
LIBC.mincore.restype = ctypes.c_int
LIBC.munmap.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
LIBC.munmap.restype = ctypes.c_int


class IOVec(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("size", ctypes.c_size_t)]


PREADV2 = getattr(LIBC, "preadv2", None)
if PREADV2 is not None:
    PREADV2.argtypes = (ctypes.c_int, ctypes.POINTER(IOVec), ctypes.c_int, ctypes.c_int64, ctypes.c_int)
    PREADV2.restype = ctypes.c_ssize_t


class CacheSourceUnavailable(OSError):
    """The exact detached source did not pass cache admission."""


@dataclass(frozen=True)
class Extent:
    size: int
    sha256: str
    kind: str


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mode, info.st_nlink, info.st_mtime_ns, info.st_ctime_ns)


def thread_input_blocks():
    return getrusage(RUSAGE_THREAD).ru_inblock


def thread_io():
    with open("/proc/thread-self/io","rb") as stream:
        read_bytes = next(int(line.split(b":",1)[1]) for line in stream if line.startswith(b"read_bytes:"))
    return thread_input_blocks(),read_bytes


def resident_pages(fd, size, offset=0):
    """Passively examine a page-aligned PROT_NONE view. Never touch mapped bytes."""
    aligned = offset - offset % PAGE
    length = size + offset - aligned
    pages = (length + PAGE - 1) // PAGE
    vector = (ctypes.c_ubyte * pages)()
    address = LIBC.mmap(None,length,0,mmap.MAP_SHARED,fd,aligned)
    if address == ctypes.c_void_p(-1).value:
        error = ctypes.get_errno()
        raise CacheSourceUnavailable(error,os.strerror(error))
    try:
        if LIBC.mincore(address,length,vector):
            error = ctypes.get_errno()
            raise CacheSourceUnavailable(error,os.strerror(error))
        return sum(value & 1 for value in vector),pages
    finally:
        LIBC.munmap(address,length)


def preadv_nowait(fd, target, offset):
    # The frozen interpreter can expose os.preadv without support for nonzero flags.
    if PREADV2 is None:
        raise CacheSourceUnavailable(errno.ENOSYS, "preadv2 is unavailable")
    data = (ctypes.c_char * len(target)).from_buffer(target)
    vector = IOVec(ctypes.addressof(data), len(target))
    received = PREADV2(fd, ctypes.byref(vector), 1, offset, RWF_NOWAIT)
    if received < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return received


class CacheReader:
    def __init__(self, directory, extents):
        self.directory = directory
        self.extents = dict(extents)
        self.metadata = {}
        self.preflight = {}
        self.preflight_identities = {}
        self.fingerprints = {}
        self.read_files = set()
        self.bytes = 0
        self.returned_bytes = 0
        self.requests = 0
        self.read_input_blocks = 0
        self.read_bytes_charged = 0
        self.refused_read = None
        self.metadata_hits = 0
        self.dir_fd = None
        self.opening = None

    def __enter__(self):
        if self.directory.resolve(strict=True) != self.directory:
            raise CacheSourceUnavailable("The detached prefix must be a direct directory")
        self.dir_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            if identity(os.fstat(self.dir_fd)) != identity(self.directory.lstat()):
                raise CacheSourceUnavailable("The detached directory changed before use")
            for name,extent in self.extents.items():
                with self.open_member(name) as (fd,info):
                    present,total = resident_pages(fd,extent.size)
                    self.preflight[name] = dict(resident_pages=present,total_pages=total)
                    if present != total:
                        self.refused_read = dict(file=name,offset=None,resident_pages=present,total_pages=total,
                                                 attempted=False,condition="initial_cache_census")
                        raise CacheSourceUnavailable(f"Cold or mixed enrolled file before any data read: {name} ({present}/{total})")
                    self.preflight_identities[name] = identity(info)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        os.close(self.dir_fd)
        self.dir_fd = None

    @contextmanager
    def open_member(self,name):
        self.opening = name
        try:
            fd = os.open(name,os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,dir_fd=self.dir_fd)
        finally:
            self.opening = None
        try:
            info = os.fstat(fd)
            if not S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != self.extents[name].size:
                raise CacheSourceUnavailable(f"The booked regular-file extent changed: {name}")
            if info.st_uid != os.geteuid():
                raise CacheSourceUnavailable(f"Require inode ownership for a trustworthy mincore observation: {name}")
            yield fd,info
        finally:
            os.close(fd)

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

        with self.open_member(path.name) as (fd,first):
            if identity(first) != self.preflight_identities[path.name]:
                raise CacheSourceUnavailable(f"The enrolled file changed after its cache census: {path.name}")
            body = bytearray(extent.size)
            view = memoryview(body)
            for offset in range(0, extent.size, BLOCK):
                target = view[offset:offset + BLOCK]
                present,total = resident_pages(fd,len(target),offset)
                if present != total:
                    self.refused_read = dict(file=path.name,offset=offset,resident_pages=present,total_pages=total,
                                             attempted=False,condition="pre_call_cache_census")
                    raise CacheSourceUnavailable(f"Cold or mixed cache before data call: {path.name} at byte {offset}")
                before_blocks,before_bytes = thread_io()
                self.requests += 1
                error,received = None,0
                try:
                    received = preadv_nowait(fd,target,offset)
                except OSError as failure:
                    error = failure
                finally:
                    after_blocks,after_bytes = thread_io()
                    blocks,charged = after_blocks-before_blocks,after_bytes-before_bytes
                    self.read_input_blocks += blocks
                    self.read_bytes_charged += charged
                self.returned_bytes += received
                if error is not None or received != len(target) or blocks or charged:
                    self.refused_read = dict(file=path.name,offset=offset,returned_bytes=received,
                        charged_input_blocks=blocks,charged_read_bytes=charged,attempted=True,
                        syscall_errno=None if error is None else error.errno,
                        condition="incidental_read_charge" if blocks or charged else "nowait_refused")
                    reason = "short or physical read" if error is None else error.strerror
                    raise CacheSourceUnavailable(f"Detached read refused for {path.name} at byte {offset}: {reason}") from error
                self.bytes += received
            if (identity(first) != identity(os.fstat(fd))
                    or identity(first) != identity(os.stat(path.name, dir_fd=self.dir_fd, follow_symlinks=False))
                    or identity(os.fstat(self.dir_fd)) != identity(self.directory.lstat())):
                raise CacheSourceUnavailable(f"The detached source changed while reading: {path.name}")
            if "sha256:" + sha256(body).hexdigest() != extent.sha256:
                raise CacheSourceUnavailable(f"The detached source differs from the signed enrollment: {path.name}")
        self.read_files.add(path.name)
        self.fingerprints[path.name] = identity(first)
        if extent.kind in {"manifest", "index"}:
            self.metadata[path.name] = bytes(body)
            return self.metadata[path.name]
        return body

    def receipt(self):
        return dict(files=sorted(self.read_files), bytes=self.bytes, nowait_requests=self.requests,
                    returned_bytes=self.returned_bytes,read_input_blocks=self.read_input_blocks,
                    charged_read_bytes=self.read_bytes_charged,refused_read=self.refused_read,
                    passive_preflight=self.preflight,metadata_reuses=self.metadata_hits,persistent_copy_bytes=0)

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
