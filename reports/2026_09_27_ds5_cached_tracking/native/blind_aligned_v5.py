"""Dual-RX aligned blind ingress with an ARM-safe NEON layout contract."""

from __future__ import annotations

import ctypes as ct
import json
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

from known_state import DEPLOY, HERE, NATIVE, sha256
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.native_presence import array, pointer
from tools.presence_dwell import DwellResult
from tools.presence_window_rank import RankScreens, read_screens


def build_library_v5(output: Path = HERE / "libblind_aligned_v5.so") -> Path:
    output = output.resolve()
    receipt_path = output.with_name(output.name + ".build.json")
    if output.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if sha256(output) != receipt["binary_sha256"]:
            raise ValueError("V5 binary does not match receipt")
        for source, expected in receipt["sources_sha256"].items():
            if sha256(Path(source)) != expected:
                raise ValueError(f"V5 source changed: {source}")
        return output
    if output.exists() or receipt_path.exists():
        raise ValueError("partial V5 build")
    profile_path = HERE / "profile.json"
    profile = json.loads(profile_path.read_text())
    compiler = shutil.which("cc")
    if compiler is None:
        raise FileNotFoundError("cc")
    sources = [
        HERE / name
        for name in (
            "known_state.c", "known_state.h", "known_state_v2.c", "known_state_v2.h",
            "known_state_v3.c", "known_state_v3.h", "blind_strided_v4.c",
            "blind_strided_v4.h", "blind_aligned_v5.c", "blind_aligned_v5.h",
            "blind_aligned_v5.py", "profile.json",
        )
    ]
    sources += sorted(NATIVE.glob("*.[ch]"))
    sources.append(DEPLOY / "src/leo/analysis/starlink/_native_acquisition_grid.inc")
    hashes = {str(path.resolve()): sha256(path) for path in sources}
    command = [
        compiler, "-std=c11", "-O3", "-fno-math-errno", "-Wall", "-Wextra",
        "-Werror", *profile["flags"], "-shared", "-fPIC", "-I", str(NATIVE),
        "-I", str(HERE), str(HERE / "blind_aligned_v5.c"), str(NATIVE / "fft.c"),
        "-lm", "-o", str(output),
    ]
    subprocess.run(command, check=True)
    if hashes != {str(path.resolve()): sha256(path) for path in sources}:
        raise ValueError("V5 source changed during build")
    receipt = {
        "schema": "org.leo.research.blind-aligned-v5-build/v1",
        "created_unix_ns": time.time_ns(),
        "command": command,
        "compiler_version": subprocess.run(
            [compiler, "--version"], check=True, text=True, capture_output=True
        ).stdout,
        "compiler_sha256": sha256(Path(compiler).resolve()),
        "sources_sha256": hashes,
        "binary_sha256": sha256(output),
    }
    with receipt_path.open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return output


class NativeAlignedBlindV5:
    def __init__(
        self,
        rate: int,
        edge: str,
        library: Path | None = None,
        *,
        bins: int = 512,
        timing_bins: int | None = None,
    ):
        if (
            type(rate) is not int or rate not in (2_500_000, 5_000_000)
            or edge not in ("lower", "upper")
            or type(bins) is not int or bins not in (512, 1024, 2048, 4096, 8192)
            or timing_bins is not None and (
                type(timing_bins) is not int
                or timing_bins not in (512, 1024, 2048, 4096, 8192)
            )
        ):
            raise ValueError("unsupported V5 blind geometry")
        self.rate = rate
        self.library = ct.CDLL(str(build_library_v5() if library is None else library))
        self.library.leo_blind_aligned_v5_create.argtypes = [
            ct.c_uint32, ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.c_uint32,
        ]
        self.library.leo_blind_aligned_v5_create.restype = ct.c_void_p
        self.library.leo_blind_aligned_v5_destroy.argtypes = [ct.c_void_p]
        self.library.leo_blind_aligned_v5_destroy.restype = None
        self.library.leo_blind_aligned_v5_run_ci16.argtypes = [
            ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.c_uint32,
            ct.c_uint32, ct.POINTER(DwellResult),
        ]
        self.library.leo_blind_aligned_v5_run_ci16.restype = ct.c_int
        self.library.leo_blind_aligned_v5_get_screens.argtypes = [
            ct.c_void_p, ct.POINTER(RankScreens),
        ]
        self.library.leo_blind_aligned_v5_get_screens.restype = ct.c_int
        exact, control = [
            array(qin_edge_pilot_frame(rate, edge, symbol_roll=roll))
            for roll in (0, 17)
        ]
        self.workspace = self.library.leo_blind_aligned_v5_create(
            rate, pointer(exact), pointer(control), len(exact), bins, timing_bins or 0
        )
        if not self.workspace:
            raise ValueError("V5 blind initialization failed")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.workspace:
            self.library.leo_blind_aligned_v5_destroy(self.workspace)
            self.workspace = None

    def run(self, raw_iq, receiver: int, *, maximum=6, seeded=True):
        values = np.asarray(raw_iq)
        if (
            not self.workspace or values.dtype != np.dtype("int16")
            or values.shape != (self.rate // 50 * 6, 2, 2)
            or values.strides != (8, 4, 2) or not values.flags.c_contiguous
            or type(receiver) is not int or receiver not in (0, 1)
            or type(maximum) is not int or not 1 <= maximum <= 6
            or type(seeded) is not bool
        ):
            raise ValueError("sample-aligned C-contiguous dual-RX CI16 dwell required")
        result = DwellResult()
        if self.library.leo_blind_aligned_v5_run_ci16(
            self.workspace, values.ctypes.data_as(ct.c_void_p), len(values), receiver,
            maximum, int(seeded), ct.byref(result),
        ):
            raise ValueError("V5 blind run rejected input")
        return result

    def screens(self):
        return read_screens(
            self.library, self.workspace, "leo_blind_aligned_v5_get_screens"
        )
