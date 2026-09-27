"""V3 known-state port with separate scoring and expected physical CFO."""

from __future__ import annotations

import ctypes as ct
import json
import math
import shutil
import subprocess
import time
from pathlib import Path

from known_state import DEPLOY, HERE, NATIVE, sha256
from known_state_v2 import KnownStateV2Result, NativeKnownStateV2


class KnownStateV3Result(ct.Structure):
    _fields_ = [
        ("score", KnownStateV2Result),
        ("expected_physical_cfo_hz", ct.c_double),
        ("cfo_residual_from_scored_hz", ct.c_double),
        ("physical_cfo_innovation_hz", ct.c_double),
    ]


def build_library_v3(output: Path = HERE / "libknown_state_v3.so") -> Path:
    output = output.resolve()
    receipt_path = output.with_name(output.name + ".build.json")
    if output.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if sha256(output) != receipt["binary_sha256"]:
            raise ValueError("V3 binary does not match receipt")
        for source, expected in receipt["sources_sha256"].items():
            if sha256(Path(source)) != expected:
                raise ValueError(f"V3 source changed: {source}")
        return output
    if output.exists() or receipt_path.exists():
        raise ValueError("partial V3 build")
    profile_path = HERE / "profile.json"
    profile = json.loads(profile_path.read_text())
    compiler = shutil.which("cc")
    if compiler is None:
        raise FileNotFoundError("cc")
    sources = [
        HERE / name
        for name in (
            "known_state.c", "known_state.h", "known_state_v2.c", "known_state_v2.h",
            "known_state_v3.c", "known_state_v3.h", "known_state_v3.py", "profile.json",
        )
    ]
    sources += sorted(NATIVE.glob("*.[ch]"))
    sources.append(DEPLOY / "src/leo/analysis/starlink/_native_acquisition_grid.inc")
    hashes = {str(path.resolve()): sha256(path) for path in sources}
    command = [
        compiler, "-std=c11", "-O3", "-fno-math-errno", "-Wall", "-Wextra",
        "-Werror", *profile["flags"], "-shared", "-fPIC", "-I", str(NATIVE),
        "-I", str(HERE), str(HERE / "known_state_v3.c"), str(NATIVE / "fft.c"),
        str(NATIVE / "window_rank.c"), str(NATIVE / "dwell.c"), "-lm", "-o", str(output),
    ]
    subprocess.run(command, check=True)
    if hashes != {str(path.resolve()): sha256(path) for path in sources}:
        raise ValueError("V3 source changed during build")
    receipt = {
        "schema": "org.leo.research.known-state-v3-build/v1",
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


class NativeKnownStateV3(NativeKnownStateV2):
    def __init__(self, rate: int, edge: str, library: Path | None = None):
        super().__init__(rate, edge, build_library_v3() if library is None else library)
        self.library.leo_known_state_v3_measure_ci16.argtypes = [
            ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.c_double,
            ct.c_double, ct.c_double, ct.c_uint32, ct.c_uint32,
            ct.POINTER(KnownStateV3Result),
        ]
        self.library.leo_known_state_v3_measure_ci16.restype = ct.c_int

    def measure(self, iq, epoch_samples: float, scored_cfo_hz: float, *,
                expected_physical_cfo_hz: float | None = None,
                recover_timing=False, frame_limit=16):
        values = self._validate_view(iq, recover_timing, frame_limit)
        expected = scored_cfo_hz if expected_physical_cfo_hz is None else expected_physical_cfo_hz
        if not math.isfinite(float(expected)):
            raise ValueError("finite expected physical CFO required")
        result = KnownStateV3Result()
        if self.library.leo_known_state_v3_measure_ci16(
            self.workspace, values.ctypes.data_as(ct.c_void_p), len(values),
            values.strides[0] // 2, float(epoch_samples), float(scored_cfo_hz),
            float(expected), int(recover_timing), frame_limit, ct.byref(result),
        ):
            raise ValueError("V3 measurement rejected state or samples")
        score = result.score
        output = {name: getattr(score, name) for name, _ in score._fields_}
        output.update(
            expected_physical_cfo_hz=result.expected_physical_cfo_hz,
            cfo_residual_from_scored_hz=result.cfo_residual_from_scored_hz,
            physical_cfo_innovation_hz=result.physical_cfo_innovation_hz,
            timing_semantics=(
                "locally_refined" if recover_timing and score.timing_bracketed else
                "local_recovery_failed" if recover_timing else "predicted_verified"
            ),
            score_semantics=(
                "full_aperture_final_glrt" if frame_limit == 16
                else f"partial_{frame_limit}_frame_final_glrt_unqualified"
            ),
            cfo_innovation_within_8khz=not bool(score.status & 2),
            needs_reacquire=bool(score.status),
            epoch_samples=(score.epoch + score.fractional_offset_samples)
            % (self.rate / 750.0),
            timing_bracket_status=(
                "not_searched" if not score.timing_search_performed else
                "bracketed" if score.timing_bracketed else "edge_needs_reacquisition"
            ),
        )
        return output

    def _validate_view(self, iq, recover_timing, frame_limit):
        import numpy as np

        values = np.asarray(iq)
        if (
            not self.workspace or values.dtype != np.dtype("int16")
            or values.shape != (self.rate // 50, 2) or values.strides[1] != 2
            or values.strides[0] % 2 or not 2 <= values.strides[0] // 2 <= 16
            or type(recover_timing) is not bool or frame_limit not in (2, 4, 16)
        ):
            raise ValueError("one positive-stride selected 20 ms CI16 RX view is required")
        return values
