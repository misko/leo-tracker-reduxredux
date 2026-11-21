"""Find a second carrier by subtracting one fitted pilot and rechecking the original I/Q."""

import ctypes as ct
import hashlib
import os
import subprocess
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame

from . import timing_first_receiver as timing

SOURCE = Path(__file__).with_name("pilot_cancel.c")
HEADER = SOURCE.with_suffix(".h")


def build(directory):
    directory.mkdir(exist_ok=True, parents=True)
    cc = os.environ.get("CC", "cc")
    signature = hashlib.sha256(
        SOURCE.read_bytes() + HEADER.read_bytes() + repr([cc, *timing.FLAGS]).encode()
    ).hexdigest()[:16]
    path = directory / ("pilot-cancel-" + signature + ".so")
    if not path.exists():
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        subprocess.run(
            [cc, *timing.FLAGS, "-shared", "-fPIC", str(SOURCE), "-lm", "-o", str(tmp)], check=True
        )
        tmp.replace(path)
    return timing.build(directory), path


def same(a, b):
    dt = abs((a["epoch"] - b["epoch"] + 6666.5) % 13333 - 6666.5)
    return dt <= 2 and abs(a["hz"] - b["hz"]) <= 1000


class Receiver:
    def __init__(self, binaries, edge):
        self.base = timing.Receiver(binaries[0], edge)
        self.lib = ct.CDLL(str(binaries[1]))
        self.lib.pilot_cancel.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_int,
            ct.c_void_p,
            ct.c_void_p,
            ct.c_double,
            ct.c_double,
        ]
        self.pilot = qin_edge_pilot_frame(30000000, edge)
        self.rotated = np.empty(40000, dtype=np.complex64)
        self.residual = np.empty((200000, 2, 2), dtype="<i2")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.base.__exit__(*exc)

    def cancel(self, iq, lane, first):
        if (
            iq.shape != self.residual.shape
            or iq.dtype != self.residual.dtype
            or not iq.flags.c_contiguous
            or self.lib.pilot_cancel(
                iq.ctypes.data,
                self.residual.ctypes.data,
                lane,
                self.pilot.ctypes.data,
                self.rotated.ctypes.data,
                first["epoch"],
                first["hz"],
            )
        ):
            raise ValueError("invalid signed capture or pilot cancellation parameters")
        return self.residual

    def __call__(self, iq, lane, lo, hi):
        first = self.base(iq, lane, lo, hi)
        if first is None:
            return []
        second = self.base(self.cancel(iq, lane, first), lane, lo, hi)
        return [first, second] if second is not None and not same(first, second) else [first]
