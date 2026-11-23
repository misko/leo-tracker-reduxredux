"""Matched Zstandard stream reader for an authenticated research member."""

from contextlib import ExitStack, contextmanager
import ctypes as ct
import subprocess
from time import process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from .signed_ingress_reuse import measured_ingress


class Buffer(ct.Structure):
    _fields_ = [("data", ct.c_void_p), ("size", ct.c_size_t), ("pos", ct.c_size_t)]


_bytes_new = ct.pythonapi.PyBytes_FromStringAndSize
_bytes_new.argtypes, _bytes_new.restype = (ct.c_void_p, ct.c_ssize_t), ct.py_object
_bytes_data = ct.pythonapi.PyBytes_AsString
_bytes_data.argtypes, _bytes_data.restype = (ct.py_object,), ct.c_void_p


def local_resolver(path):
    """Find the pinned C extension's private libzstd symbols using its ELF table."""
    library = ct.CDLL(str(path))
    symbols = {}
    for line in subprocess.check_output(["nm", "--defined-only", str(path)], text=True).splitlines():
        address, kind, name = line.split(maxsplit=2)
        if kind in ("t", "T"):
            symbols[name] = int(address, 16)
    base = ct.cast(library.PyInit_backend_c, ct.c_void_p).value - symbols["PyInit_backend_c"]

    def resolve(name, _library=library):
        return base + symbols[name]

    return resolve


class Backend:
    def __init__(self, resolve):
        self.resolve = resolve

        def connect(name, result, *args):
            return ct.CFUNCTYPE(result, *args)(resolve("ZSTD_" + name))

        self.version = connect("versionNumber", ct.c_uint)()
        self.create = connect("createDStream", ct.c_void_p)
        self.init = connect("initDStream", ct.c_size_t, ct.c_void_p)
        self.free = connect("freeDStream", ct.c_size_t, ct.c_void_p)
        self.frame_size = connect("findFrameCompressedSize", ct.c_size_t, ct.c_void_p, ct.c_size_t)
        self.step = connect("decompressStream", ct.c_size_t, ct.c_void_p, ct.POINTER(Buffer), ct.POINTER(Buffer))
        self.is_error = connect("isError", ct.c_uint, ct.c_size_t)

    @classmethod
    def system(cls, path):
        library = ct.CDLL(str(path))
        backend = cls(lambda name: ct.cast(getattr(library, name), ct.c_void_p).value)
        backend.library = library
        return backend


class OwnedBytesStream:
    def __init__(self, backend, source, stats, error):
        self.backend, self.source, self.stats, self.error = backend, source, stats, error
        self.input = Buffer(source.ctypes.data, source.nbytes, 0)
        self.done = False
        self.context = backend.create()
        if not self.context:
            raise MemoryError("Could not create a native Zstandard stream")
        if backend.is_error(backend.init(self.context)):
            self.close()
            raise error("Could not initialize native Zstandard stream")

    def close(self):
        self.backend.free(self.context)

    def read(self, size):
        if self.done or size == 0:
            return b""
        # CPython permits filling a new, unexposed bytes object built with NULL.
        result = _bytes_new(None, size)
        output = Buffer(_bytes_data(result), size, 0)
        while output.pos < size:
            before = self.input.pos, output.pos
            began = process_time_ns()
            status = self.backend.step(self.context, ct.byref(output), ct.byref(self.input))
            self.stats["step_cpu_ns"] += process_time_ns() - began
            self.stats["steps"] += 1
            if self.backend.is_error(status):
                raise self.error("Native Zstandard stream rejected the frame")
            if status == 0:
                if self.input.pos != self.input.size:
                    raise self.error("Unexpected bytes followed the standard frame")
                self.done = True
                break
            if before == (self.input.pos, output.pos):
                raise self.error("Native Zstandard stream could not drain the frame")
        return result if output.pos == size else result[:output.pos]


class ReplayOnError:
    def __init__(self, bridge, stock_reader, stack, stats):
        self.bridge, self.stock_reader, self.stack, self.stats = bridge, stock_reader, stack, stats
        self.stock = None
        self.requests = []

    def read(self, size):
        if self.stock is None:
            try:
                result = self.bridge.read(size)
                self.requests.append((size, len(result)))
                return result
            except self.bridge.error:
                self.stats["error_fallbacks"] += 1
                self.stock = self.stack.enter_context(self.stock_reader())
                for prior_size, prior_length in self.requests:
                    if len(self.stock.read(prior_size)) != prior_length:
                        raise self.bridge.error("Original Zstandard stream returned a different extent")
        return self.stock.read(size)


class StreamBridge:
    def __init__(self, backend, stock, stats):
        self.backend, self.stock, self.stats = backend, stock, stats

    @contextmanager
    def stream_reader(self, compressed):
        def stock_reader():
            return self.stock.ZstdDecompressor().stream_reader(compressed)

        began = process_time_ns()
        source = np.frombuffer(compressed, dtype=np.uint8)
        shape = (memoryview(compressed)[:4] == b"\x28\xb5\x2f\xfd"
                 and self.backend.frame_size(source.ctypes.data, source.nbytes) == source.nbytes)
        self.stats["shape_cpu_ns"] += process_time_ns() - began
        if not shape:
            self.stats["layout_fallbacks"] += 1
            with stock_reader() as reader:
                yield reader
            return
        self.stats["standard_frames"] += 1
        with ExitStack() as stack:
            bridge = OwnedBytesStream(self.backend, source, self.stats, self.stock.ZstdError)
            stack.callback(bridge.close)
            yield ReplayOnError(bridge, stock_reader, stack, self.stats)


@contextmanager
def timed_decoder(buffer, costs, backend, stats):
    from leo.storage import short_window

    if backend is None:
        with measured_ingress(buffer, costs):
            yield
        return
    stock = short_window.zstd
    adapter = SimpleNamespace(ZstdError=stock.ZstdError,
                              ZstdDecompressor=lambda: StreamBridge(backend, stock, stats))
    with patch.object(short_window, "zstd", adapter), measured_ingress(buffer, costs):
        yield
