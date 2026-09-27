"""Binding/build receipt for the fractional coefficient-transpose GLRT."""

from __future__ import annotations

import ctypes as ct
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NATIVE_REPORT = ROOT / "native"
sys.path.insert(0, str(NATIVE_REPORT))

from known_state import DEPLOY, NATIVE, sha256  # noqa: E402
from known_state_v2 import KnownStateV2Result  # noqa: E402
from leo.analysis.starlink.templates import qin_edge_pilot_frame  # noqa: E402
from tools.native_presence import array, pointer  # noqa: E402


class CoeffResult(ct.Structure):
    _fields_ = [
        ("score", KnownStateV2Result),
        ("coefficient_tables_built", ct.c_uint32),
        ("coefficient_table_hits", ct.c_uint32),
        *[
            (name, ct.c_double)
            for name in (
                "coefficient_build_cpu_ms",
                "coefficient_dot_cpu_ms",
                "correlation_max_abs_error",
                "correlation_max_relative_error",
                "ceiling_max_abs_error",
                "ceiling_max_relative_error",
                "baseline_exact_score",
                "baseline_control_score",
                "baseline_cfo_residual_hz",
            )
        ],
        ("baseline_peak_bin", ct.c_uint32),
        ("coefficient_peak_bin", ct.c_uint32),
    ]


def build_library(output: Path = HERE / "libcoeff_glrt.so") -> Path:
    output = output.resolve()
    receipt_path = output.with_name(output.name + ".build.json")
    if output.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if sha256(output) != receipt["binary_sha256"]:
            raise ValueError("coefficient binary does not match receipt")
        for source, expected in receipt["sources_sha256"].items():
            if sha256(Path(source)) != expected:
                raise ValueError(f"coefficient source changed: {source}")
        return output
    if output.exists() or receipt_path.exists():
        raise ValueError("partial coefficient build")
    profile_path = NATIVE_REPORT / "profile.json"
    profile = json.loads(profile_path.read_text())
    compiler = shutil.which("cc")
    if compiler is None:
        raise FileNotFoundError("cc")
    sources = [HERE / name for name in ("coeff_glrt.c", "coeff_glrt.h", "coeff_glrt.py")]
    sources += [
        NATIVE_REPORT / name
        for name in ("known_state.c", "known_state.h", "known_state_v2.c", "known_state_v2.h")
    ]
    sources += sorted(NATIVE.glob("*.[ch]"))
    sources += [
        DEPLOY / "src/leo/analysis/starlink/_native_acquisition_grid.inc",
        profile_path,
    ]
    hashes = {str(path.resolve()): sha256(path) for path in sources}
    command = [
        compiler, "-std=c11", "-O3", "-fno-math-errno", "-Wall", "-Wextra",
        "-Werror", *profile["flags"], "-shared", "-fPIC", "-I", str(NATIVE),
        "-I", str(NATIVE_REPORT), "-I", str(HERE), str(HERE / "coeff_glrt.c"),
        str(NATIVE / "fft.c"), "-lm", "-o", str(output),
    ]
    subprocess.run(command, check=True)
    if hashes != {str(path.resolve()): sha256(path) for path in sources}:
        raise ValueError("coefficient source changed during build")
    receipt = {
        "schema": "org.leo.research.coefficient-glrt-build/v1",
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


class NativeCoeffGLRT:
    def __init__(self, rate: int, edge: str, library: Path | None = None):
        if type(rate) is not int or rate not in (2_500_000, 5_000_000) or edge not in (
            "lower", "upper"
        ):
            raise ValueError("unsupported coefficient GLRT geometry")
        self.rate = rate
        self.library = ct.CDLL(str(build_library() if library is None else library))
        self.library.leo_coeff_create.argtypes = [
            ct.c_uint32, ct.c_void_p, ct.c_void_p, ct.c_size_t,
        ]
        self.library.leo_coeff_create.restype = ct.c_void_p
        self.library.leo_coeff_destroy.argtypes = [ct.c_void_p]
        self.library.leo_coeff_destroy.restype = None
        self.library.leo_coeff_measure_ci16.argtypes = [
            ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.c_double,
            ct.c_double, ct.POINTER(CoeffResult),
        ]
        self.library.leo_coeff_measure_ci16.restype = ct.c_int
        exact, control = [
            array(qin_edge_pilot_frame(rate, edge, symbol_roll=roll))
            for roll in (0, 17)
        ]
        self.workspace = self.library.leo_coeff_create(
            rate, pointer(exact), pointer(control), len(exact)
        )
        if not self.workspace:
            raise ValueError("coefficient GLRT initialization failed")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.workspace:
            self.library.leo_coeff_destroy(self.workspace)
            self.workspace = None

    def measure(self, iq, epoch_samples: float, scored_cfo_hz: float):
        values = np.asarray(iq)
        if (
            not self.workspace or values.dtype != np.dtype("int16")
            or values.shape != (self.rate // 50, 2) or values.strides[1] != 2
            or values.strides[0] % 2 or not 2 <= values.strides[0] // 2 <= 16
        ):
            raise ValueError("one positive-stride selected 20 ms CI16 RX view is required")
        result = CoeffResult()
        if self.library.leo_coeff_measure_ci16(
            self.workspace, values.ctypes.data_as(ct.c_void_p), len(values),
            values.strides[0] // 2, float(epoch_samples), float(scored_cfo_hz),
            ct.byref(result),
        ):
            raise ValueError("coefficient GLRT rejected input or bounds")
        output = {name: getattr(result.score, name) for name, _ in result.score._fields_}
        output.update(
            (name, getattr(result, name))
            for name, _ in result._fields_ if name != "score"
        )
        output["margin"] = output["exact_score"] - output["control_score"]
        output["baseline_margin"] = (
            output["baseline_exact_score"] - output["baseline_control_score"]
        )
        output["score_semantics"] = (
            "unchanged_integer_full_aperture_glrt"
            if abs(output["fractional_offset_samples"] - round(output["fractional_offset_samples"]))
            <= 1e-12 else "fractional_coefficient_transpose_full_aperture_research"
        )
        return output
