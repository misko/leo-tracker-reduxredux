"""Small, explicit text-only cache for a guarded source verification scope."""

from collections import OrderedDict
from hashlib import sha256
from importlib.machinery import SourceFileLoader
from inspect import getsource
from pathlib import Path
import sys
from types import FunctionType


def stamp(path):
    data = path.stat()
    return data.st_dev, data.st_ino, data.st_size, data.st_mtime_ns, data.st_ctime_ns


class VerifiedSourceText:
    """Cache source text, never globals, closures, executable code or auth results.

    Callers still apply their independently reviewed source/code guards. This
    cache only shortcuts repeated text extraction for unchanged loaded files.
    """

    def __init__(self, pins, original=getsource, limit=16):
        self.pins = {str(Path(path)): pin for path, pin in pins.items()}
        self.original = original
        self.limit = limit
        self.entries = OrderedDict()

    def source(self, operation):
        if type(operation) is not FunctionType or hasattr(operation, "__wrapped__"):
            return self.original(operation)
        code, globals_ = operation.__code__, operation.__globals__
        module = sys.modules.get(operation.__module__)
        spec = getattr(module, "__spec__", None)
        loader = getattr(spec, "loader", None)
        filename = code.co_filename
        pin = self.pins.get(filename)
        if (pin is None or getattr(module, "__dict__", None) is not globals_
                or type(loader) is not SourceFileLoader or spec.origin != filename
                or module.__loader__ is not loader or loader.path != filename):
            return self.original(operation)
        path = Path(filename)
        try:
            current = stamp(path)
        except OSError:
            self.entries.pop(operation, None)
            return self.original(operation)
        previous = self.entries.get(operation)
        if (previous is not None and previous[0] is code and previous[1] is module
                and previous[2] is loader and previous[3] == (pin, current)):
            self.entries.move_to_end(operation)
            return previous[4]
        self.entries.pop(operation, None)
        text = self.original(operation)
        try:
            verified = sha256(path.read_bytes()).hexdigest() == pin and stamp(path) == current
        except OSError:
            verified = False
        if verified:
            self.entries[operation] = code, module, loader, (pin, current), text
            if len(self.entries) > self.limit:
                self.entries.popitem(last=False)
        return text
