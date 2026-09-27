"""ctypes/build port for the bounded known-state final GLRT experiment."""

from __future__ import annotations

import ctypes as ct
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
NATIVE = DEPLOY / "src/leo/analysis/native_presence"
sys.path[:0] = [str(DEPLOY), str(DEPLOY / "src")]

from leo.analysis.starlink.templates import qin_edge_pilot_frame  # noqa: E402


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


class KnownStateResult(ct.Structure):
    _fields_ = [
        *[
            (name, ct.c_uint32)
            for name in (
                "schema_version",
                "mode",
                "status",
                "scored_fractional",
                "timing_search_performed",
                "timing_bracketed",
                "support_frames",
                "glrt_evaluations",
                "valid_bounds",
            )
        ],
        ("epoch", ct.c_int32),
        *[
            (name, ct.c_double)
            for name in (
                "fractional_offset_samples",
                "predicted_epoch_samples",
                "predicted_cfo_hz",
                "scored_cfo_hz",
                "tracking_cfo_hz",
                "cfo_innovation_hz",
                "exact_score",
                "control_score",
                "margin",
                "conversion_cpu_ms",
                "kernel_cpu_ms",
                "total_cpu_ms",
                "total_wall_ms",
            )
        ],
    ]


def _pointer(values: np.ndarray):
    return values.ctypes.data_as(ct.c_void_p)


def build_library(output: Path = HERE / "libknown_state.so") -> Path:
    output = output.resolve()
    receipt_path = output.with_name(output.name + ".build.json")
    if output.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if sha256(output) != receipt["binary_sha256"]:
            raise ValueError("known-state binary does not match receipt")
        for source, expected in receipt["sources_sha256"].items():
            if sha256(Path(source)) != expected:
                raise ValueError(f"known-state source changed: {source}")
        return output
    if output.exists() or receipt_path.exists():
        raise ValueError("partial known-state build")
    profile_path = HERE / "profile.json"
    profile = json.loads(profile_path.read_text())
    base_receipt_path = ROOT / profile["base_profile"]
    if sha256(base_receipt_path) != profile["base_profile_sha256"]:
        raise ValueError("decision-band base profile receipt changed")
    base = json.loads(base_receipt_path.read_text())
    for source, expected in base["sources_sha256"].items():
        path = Path(source)
        if path.is_file() and sha256(path) != expected:
            raise ValueError(f"base-profile source changed: {path}")
    compiler = shutil.which("cc")
    if compiler is None:
        raise FileNotFoundError("cc")
    sources = [HERE / "known_state.c", HERE / "known_state.h", profile_path]
    sources += sorted(NATIVE.glob("*.[ch]"))
    sources.append(DEPLOY / "src/leo/analysis/starlink/_native_acquisition_grid.inc")
    hashes = {str(path.resolve()): sha256(path) for path in sources}
    command = [
        compiler,
        "-std=c11",
        "-O3",
        "-fno-math-errno",
        "-Wall",
        "-Wextra",
        "-Werror",
        *profile["flags"],
        "-shared",
        "-fPIC",
        "-I",
        str(NATIVE),
        str(HERE / "known_state.c"),
        str(NATIVE / "fft.c"),
        str(NATIVE / "window_rank.c"),
        str(NATIVE / "dwell.c"),
        "-lm",
        "-o",
        str(output),
    ]
    subprocess.run(command, check=True)
    if hashes != {str(path.resolve()): sha256(path) for path in sources}:
        raise ValueError("source changed during known-state build")
    receipt = {
        "schema": "org.leo.research.known-state-build/v1",
        "created_unix_ns": time.time_ns(),
        "base_profile_receipt_sha256": sha256(base_receipt_path),
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


class NativeKnownState:
    def __init__(self, rate: int, edge: str, library: Path | None = None):
        if rate not in (2_500_000, 5_000_000) or edge not in ("lower", "upper"):
            raise ValueError("supported rate and edge required")
        self.rate = rate
        self.library_path = build_library() if library is None else library.resolve()
        self.library = ct.CDLL(str(self.library_path))
        self.library.leo_known_state_create.argtypes = [
            ct.c_uint32,
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
        ]
        self.library.leo_known_state_create.restype = ct.c_void_p
        self.library.leo_known_state_destroy.argtypes = [ct.c_void_p]
        self.library.leo_known_state_measure_ci16.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_double,
            ct.c_double,
            ct.c_uint32,
            ct.POINTER(KnownStateResult),
        ]
        self.library.leo_known_state_measure_ci16.restype = ct.c_int
        exact = np.ascontiguousarray(qin_edge_pilot_frame(rate, edge), dtype=np.complex128)
        control = np.ascontiguousarray(
            qin_edge_pilot_frame(rate, edge, symbol_roll=17), dtype=np.complex128
        )
        self.workspace = self.library.leo_known_state_create(
            rate, _pointer(exact), _pointer(control), len(exact)
        )
        if not self.workspace:
            raise ValueError("known-state workspace rejected geometry")

    def close(self):
        if self.workspace:
            self.library.leo_known_state_destroy(self.workspace)
            self.workspace = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def measure(self, iq, epoch_samples: float, cfo_hz: float, *, recover_timing=False):
        values = np.asarray(iq)
        if (
            not self.workspace
            or values.dtype != np.dtype("int16")
            or values.shape != (self.rate // 50, 2)
            or type(recover_timing) is not bool
        ):
            raise ValueError("one selected 20 ms CI16 interval is required")
        values = np.ascontiguousarray(values)
        result = KnownStateResult()
        if self.library.leo_known_state_measure_ci16(
            self.workspace,
            _pointer(values),
            len(values),
            float(epoch_samples),
            float(cfo_hz),
            int(recover_timing),
            ct.byref(result),
        ):
            raise ValueError("known-state measurement rejected state or samples")
        output = {name: getattr(result, name) for name, _ in result._fields_}
        output["timing_semantics"] = (
            "locally_refined" if recover_timing and result.timing_bracketed else
            "local_recovery_failed" if recover_timing else "predicted_verified"
        )
        output["cfo_innovation_within_8khz"] = not bool(result.status & 2)
        output["needs_reacquisition"] = bool(result.status)
        output["needs_reacquire"] = output["needs_reacquisition"]
        output["epoch_samples"] = (
            result.epoch + result.fractional_offset_samples
        ) % (self.rate / 750.0)
        output["timing_bracket_status"] = (
            "not_searched" if not result.timing_search_performed else
            "bracketed" if result.timing_bracketed else "edge_needs_reacquisition"
        )
        return output
