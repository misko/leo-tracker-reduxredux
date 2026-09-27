"""V2 known-state port: natural dual-RX strides and selective conversion."""

from __future__ import annotations

import ctypes as ct
import json
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

from known_state import DEPLOY, HERE, NATIVE, NativeKnownState, sha256


class KnownStateV2Result(ct.Structure):
    _fields_ = [
        *[
            (name, ct.c_uint32)
            for name in (
                "schema_version", "mode", "status", "scored_fractional",
                "timing_search_performed", "timing_bracketed", "support_frames",
                "available_support_frames", "frame_limit", "glrt_evaluations",
                "valid_bounds", "sample_stride_i16", "converted_samples",
            )
        ],
        ("epoch", ct.c_int32),
        *[
            (name, ct.c_double)
            for name in (
                "fractional_offset_samples", "predicted_epoch_samples",
                "predicted_cfo_hz", "scored_cfo_hz", "tracking_cfo_hz",
                "cfo_innovation_hz", "exact_score", "control_score", "margin",
                "conversion_cpu_ms", "kernel_cpu_ms", "total_cpu_ms", "total_wall_ms",
            )
        ],
    ]


def build_library_v2(output: Path = HERE / "libknown_state_v2.so") -> Path:
    output = output.resolve()
    receipt_path = output.with_name(output.name + ".build.json")
    if output.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if sha256(output) != receipt["binary_sha256"]:
            raise ValueError("V2 binary does not match receipt")
        for source, expected in receipt["sources_sha256"].items():
            if sha256(Path(source)) != expected:
                raise ValueError(f"V2 source changed: {source}")
        return output
    if output.exists() or receipt_path.exists():
        raise ValueError("partial V2 build")
    profile_path = HERE / "profile.json"
    profile = json.loads(profile_path.read_text())
    compiler = shutil.which("cc")
    if compiler is None:
        raise FileNotFoundError("cc")
    sources = [
        HERE / name
        for name in (
            "known_state.c", "known_state.h", "known_state_v2.c", "known_state_v2.h",
            "known_state_v2.py", "profile.json",
        )
    ]
    sources += sorted(NATIVE.glob("*.[ch]"))
    sources.append(DEPLOY / "src/leo/analysis/starlink/_native_acquisition_grid.inc")
    hashes = {str(path.resolve()): sha256(path) for path in sources}
    command = [
        compiler, "-std=c11", "-O3", "-fno-math-errno", "-Wall", "-Wextra",
        "-Werror", *profile["flags"], "-shared", "-fPIC", "-I", str(NATIVE),
        "-I", str(HERE), str(HERE / "known_state_v2.c"), str(NATIVE / "fft.c"),
        str(NATIVE / "window_rank.c"), str(NATIVE / "dwell.c"), "-lm", "-o", str(output),
    ]
    subprocess.run(command, check=True)
    if hashes != {str(path.resolve()): sha256(path) for path in sources}:
        raise ValueError("V2 source changed during build")
    receipt = {
        "schema": "org.leo.research.known-state-v2-build/v1",
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


class NativeKnownStateV2(NativeKnownState):
    def __init__(self, rate: int, edge: str, library: Path | None = None):
        super().__init__(rate, edge, build_library_v2() if library is None else library)
        self.library.leo_known_state_v2_measure_ci16.argtypes = [
            ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.c_double,
            ct.c_double, ct.c_uint32, ct.c_uint32, ct.POINTER(KnownStateV2Result),
        ]
        self.library.leo_known_state_v2_measure_ci16.restype = ct.c_int

    def measure(self, iq, epoch_samples: float, cfo_hz: float, *,
                recover_timing=False, frame_limit=16):
        values = np.asarray(iq)
        if (
            not self.workspace or values.dtype != np.dtype("int16")
            or values.shape != (self.rate // 50, 2) or values.strides[1] != 2
            or values.strides[0] % 2 or not 2 <= values.strides[0] // 2 <= 16
            or type(recover_timing) is not bool or frame_limit not in (2, 4, 16)
        ):
            raise ValueError("one positive-stride selected 20 ms CI16 RX view is required")
        result = KnownStateV2Result()
        if self.library.leo_known_state_v2_measure_ci16(
            self.workspace, values.ctypes.data_as(ct.c_void_p), len(values),
            values.strides[0] // 2, float(epoch_samples), float(cfo_hz),
            int(recover_timing), frame_limit, ct.byref(result),
        ):
            raise ValueError("V2 measurement rejected state or samples")
        output = {name: getattr(result, name) for name, _ in result._fields_}
        output["timing_semantics"] = (
            "locally_refined" if recover_timing and result.timing_bracketed else
            "local_recovery_failed" if recover_timing else "predicted_verified"
        )
        output["score_semantics"] = (
            "full_aperture_final_glrt" if frame_limit == 16
            else f"partial_{frame_limit}_frame_final_glrt_unqualified"
        )
        output["cfo_innovation_within_8khz"] = not bool(result.status & 2)
        output["needs_reacquire"] = bool(result.status)
        output["epoch_samples"] = (
            result.epoch + result.fractional_offset_samples
        ) % (self.rate / 750.0)
        output["timing_bracket_status"] = (
            "not_searched" if not result.timing_search_performed else
            "bracketed" if result.timing_bracketed else "edge_needs_reacquisition"
        )
        return output
