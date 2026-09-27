"""Rescue-only fixed-point native GLRT with the stable blind tone fit."""

from __future__ import annotations

import ctypes as ct
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np


HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
REPO = HERE.parents[2]
SRC = REPO / "src"
TG11 = REPORT / "tg11"
RESEARCH_NATIVE = REPORT / "native"
BOUNDARY = REPORT / "native_guided_boundary"
FFT32 = REPORT / "fft32"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
DEPLOY_NATIVE = DEPLOY / "src/leo/analysis/native_presence"
SUPPORT_GUARD_HZ = 1e-6
FRAME_RATE_HZ = 750

sys.path[:0] = [str(SRC), str(TG11), str(RESEARCH_NATIVE)]
from leo.analysis.starlink.templates import qin_edge_pilot_frame  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _sources() -> list[Path]:
    own = [HERE / name for name in (
        "tone_guided_native.c", "tone_guided_native.h", "native_tone_guided.py",
    )]
    frozen = [BOUNDARY / name for name in (
        "guided_boundary_native.c", "guided_boundary_native.h",
    )] + [TG11 / name for name in ("tg11_native.c", "tg11_native.h")] + [
        RESEARCH_NATIVE / name for name in (
            "known_state.c", "known_state.h", "known_state_v2.c", "known_state_v2.h",
            "known_state_v3.c", "known_state_v3.h", "blind_strided_v4.c",
            "blind_strided_v4.h", "profile.json",
        )
    ]
    dependencies = sorted(DEPLOY_NATIVE.glob("*.[ch]")) + [
        DEPLOY / "src/leo/analysis/starlink/_native_acquisition_grid.inc",
        FFT32 / "fft32_fftw.c",
        SRC / "leo/analysis/starlink/templates.py",
        Path("/usr/include/fftw3.h"),
        Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3").resolve(),
    ]
    return own + frozen + dependencies


def verify_library(library: Path) -> dict:
    library = Path(library).resolve()
    receipt_path = library.with_name(library.name + ".build.json")
    if not library.is_file() or not receipt_path.is_file():
        raise ValueError("tone-guided library and build receipt are required")
    receipt = json.loads(receipt_path.read_text())
    sources = {str(path.resolve()): sha256(path) for path in _sources()}
    if (
        receipt.get("schema") != "org.leo.research.tone-guided-build/v1"
        or receipt.get("support_guard_hz") != SUPPORT_GUARD_HZ
        or receipt.get("sources_sha256") != sources
        or receipt.get("binary_sha256") != sha256(library)
    ):
        raise ValueError("tone-guided binary or source differs from receipt")
    return receipt


def build_library(output: Path = HERE / "libtone_guided.so") -> Path:
    output = Path(output).resolve()
    receipt_path = output.with_name(output.name + ".build.json")
    if output.exists() and receipt_path.exists():
        verify_library(output)
        return output
    if output.exists() or receipt_path.exists():
        raise ValueError("partial tone-guided build")
    compiler = shutil.which("cc")
    if compiler is None:
        raise FileNotFoundError("cc")
    profile = json.loads((RESEARCH_NATIVE / "profile.json").read_text())
    fftw = str(Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3").resolve())
    command = [
        compiler, "-std=c11", "-O3", "-fno-math-errno", "-Wall", "-Wextra",
        "-Werror", *profile["flags"], "-shared", "-fPIC", "-I", str(HERE),
        "-I", str(BOUNDARY), "-I", str(TG11), "-I", str(RESEARCH_NATIVE),
        "-I", str(DEPLOY_NATIVE), str(HERE / "tone_guided_native.c"),
        str(FFT32 / "fft32_fftw.c"), fftw, "-lm", "-o", str(output),
    ]
    sources = _sources()
    hashes = {str(path.resolve()): sha256(path) for path in sources}
    subprocess.run(command, check=True)
    if hashes != {str(path.resolve()): sha256(path) for path in sources}:
        output.unlink(missing_ok=True)
        raise ValueError("tone-guided sources changed during build")
    receipt = {
        "schema": "org.leo.research.tone-guided-build/v1",
        "created_unix_ns": time.time_ns(),
        "abi": "rescue-only fixed-point/v1",
        "support_guard_hz": SUPPORT_GUARD_HZ,
        "nuisance_semantics": (
            "full packed CI16 energy/lag fit; FP64 working-sample subtraction; "
            "one direct final GLRT without re-ingestion"
        ),
        "command": command,
        "compiler_sha256": sha256(Path(compiler).resolve()),
        "compiler_version": subprocess.run(
            [compiler, "--version"], check=True, text=True, capture_output=True
        ).stdout,
        "sources_sha256": hashes,
        "binary_sha256": sha256(output),
        "profile_sha256": sha256(RESEARCH_NATIVE / "profile.json"),
        "fft_backend": "FFTW FP32; identical backend for nuisance and final GLRT",
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    verify_library(output)
    return output


@dataclass(frozen=True, slots=True)
class ToneGuidedObservation:
    receiver: int
    probe_index: int
    probe_start_sample: int
    local_epoch_sample: float
    dwell_epoch_sample: float
    acquired_cfo_hz: float
    tracking_cfo_hz: float
    margin: float
    fractional_complete: bool
    supported: bool
    fitted: bool
    candidate_index: int
    exact_score: float
    control_score: float
    support_frames: int
    valid_bounds: bool
    status: int
    total_cpu_ms: float
    total_wall_ms: float
    expected_physical_cfo_hz: float
    cfo_residual_from_scored_hz: float
    physical_cfo_innovation_hz: float
    nuisance_enabled: bool
    nuisance_applied: bool
    nuisance_frequency_hz: float
    nuisance_spectral_fraction: float
    nuisance_fitted_power_fraction: float
    nuisance_cpu_ms: float
    pack_cpu_ms: float
    conversion_cpu_ms: float
    glrt_cpu_ms: float
    glrt_evaluations: int
    coarse_search_evaluations: int
    fine_search_evaluations: int
    conditioned_search_evaluations: int
    epoch_lattice_evaluations: int


class _NuisanceNative(ct.Structure):
    _fields_ = [
        ("enabled", ct.c_int32), ("applied", ct.c_int32),
        ("frequency_hz", ct.c_double), ("spectral_fraction", ct.c_double),
        ("fitted_power_fraction", ct.c_double), ("cpu_ms", ct.c_double),
    ]


class _ResultNative(ct.Structure):
    _fields_ = [
        ("schema_version", ct.c_uint32),
        ("probe_index", ct.c_uint32), ("support_frames", ct.c_uint32),
        ("valid_support", ct.c_uint32), ("fractional_complete", ct.c_uint32),
        ("valid_bounds", ct.c_uint32), ("status", ct.c_uint32),
        ("glrt_evaluations", ct.c_uint32),
        ("coarse_search_evaluations", ct.c_uint32),
        ("fine_search_evaluations", ct.c_uint32),
        ("conditioned_search_evaluations", ct.c_uint32),
        ("epoch_lattice_evaluations", ct.c_uint32),
        ("epoch", ct.c_int32),
        ("fractional_offset_samples", ct.c_double),
        ("scored_cfo_hz", ct.c_double), ("expected_physical_cfo_hz", ct.c_double),
        ("cfo_residual_from_scored_hz", ct.c_double),
        ("tracking_cfo_hz", ct.c_double), ("physical_cfo_innovation_hz", ct.c_double),
        ("exact_score", ct.c_double), ("control_score", ct.c_double),
        ("margin", ct.c_double), ("nuisance", _NuisanceNative),
        ("pack_cpu_ms", ct.c_double), ("conversion_cpu_ms", ct.c_double),
        ("nuisance_cpu_ms", ct.c_double), ("glrt_cpu_ms", ct.c_double),
        ("total_cpu_ms", ct.c_double), ("total_wall_ms", ct.c_double),
    ]


class NativeToneGuided:
    def __init__(
        self, rate: int, edge: str, library: Path | None = None, *, bins: int = 512
    ) -> None:
        if (
            type(rate) is not int or rate not in (2_500_000, 5_000_000)
            or edge not in ("lower", "upper") or type(bins) is not int
            or bins not in (512, 1024, 2048, 4096, 8192)
        ):
            raise ValueError("unsupported tone-guided geometry")
        resolved = build_library() if library is None else Path(library).resolve()
        verify_library(resolved)
        self.rate = rate
        self.edge = edge
        self.window = rate // 50
        self.half_window = rate // 100
        self.dwell_samples = rate * 120 // 1_000
        self.library_path = resolved
        self.library = ct.CDLL(str(resolved))
        lib = self.library
        lib.leo_tone_guided_create.argtypes = [
            ct.c_uint32, ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_uint32,
        ]
        lib.leo_tone_guided_create.restype = ct.c_void_p
        lib.leo_tone_guided_destroy.argtypes = [ct.c_void_p]
        lib.leo_tone_guided_probe_ci16.argtypes = [
            ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.c_uint32,
            ct.c_int32, ct.c_double, ct.c_double, ct.c_double,
            ct.POINTER(_ResultNative),
        ]
        lib.leo_tone_guided_probe_ci16.restype = ct.c_int
        lib.leo_tone_guided_support_guard_hz.argtypes = []
        lib.leo_tone_guided_support_guard_hz.restype = ct.c_double
        exact, control = [
            np.ascontiguousarray(
                qin_edge_pilot_frame(rate, edge, symbol_roll=roll),
                dtype=np.complex128,
            )
            for roll in (0, 17)
        ]
        self.workspace = lib.leo_tone_guided_create(
            rate,
            exact.ctypes.data_as(ct.c_void_p),
            control.ctypes.data_as(ct.c_void_p),
            len(exact),
            bins,
        )
        if not self.workspace:
            raise ValueError("tone-guided initialization failed")
        guard = float(lib.leo_tone_guided_support_guard_hz())
        if guard != SUPPORT_GUARD_HZ:
            self.close()
            raise ValueError("tone-guided binary reports an unexpected guard")
        self.support_guard_hz = guard

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self) -> None:
        if self.workspace:
            self.library.leo_tone_guided_destroy(self.workspace)
            self.workspace = None

    def _raw(self, raw, receiver: int) -> np.ndarray:
        values = np.asarray(raw)
        if (
            not self.workspace or values.dtype != np.dtype("int16")
            or values.shape != (self.dwell_samples, 2, 2)
            or not values.flags.c_contiguous or type(receiver) is not int
            or receiver not in (0, 1)
        ):
            raise ValueError("complete C-contiguous natural dual-RX CI16 dwell required")
        return values

    def _observation(self, native: _ResultNative, receiver: int) -> ToneGuidedObservation:
        flags = (
            native.valid_support, native.fractional_complete, native.valid_bounds,
            native.nuisance.enabled, native.nuisance.applied,
        )
        if (
            native.schema_version != 1 or native.probe_index >= 11
            or native.support_frames > 16 or native.glrt_evaluations != 1
            or any(value != 0 for value in (
                native.coarse_search_evaluations, native.fine_search_evaluations,
                native.conditioned_search_evaluations,
                native.epoch_lattice_evaluations,
            ))
            or any(value not in (0, 1) for value in flags)
        ):
            raise ValueError("invalid tone-guided ABI result")
        numbers = (
            native.fractional_offset_samples, native.scored_cfo_hz,
            native.expected_physical_cfo_hz, native.cfo_residual_from_scored_hz,
            native.tracking_cfo_hz, native.physical_cfo_innovation_hz,
            native.exact_score, native.control_score, native.margin,
            native.nuisance.frequency_hz, native.nuisance.spectral_fraction,
            native.nuisance.fitted_power_fraction, native.nuisance.cpu_ms,
            native.pack_cpu_ms, native.conversion_cpu_ms, native.nuisance_cpu_ms,
            native.glrt_cpu_ms, native.total_cpu_ms, native.total_wall_ms,
        )
        if not all(math.isfinite(value) for value in numbers):
            raise ValueError("non-finite tone-guided result")
        timings = numbers[-7:]
        if any(value < 0 for value in timings):
            raise ValueError("negative tone-guided timing")
        if (
            native.nuisance.spectral_fraction < 0
            or native.nuisance.fitted_power_fraction < 0
            or native.nuisance.cpu_ms != native.nuisance_cpu_ms
            or native.scored_cfo_hz + native.cfo_residual_from_scored_hz
            != native.tracking_cfo_hz
            or native.tracking_cfo_hz - native.expected_physical_cfo_hz
            != native.physical_cfo_innovation_hz
        ):
            raise ValueError("inconsistent tone-guided result")
        period = self.rate / FRAME_RATE_HZ
        local = (native.epoch + native.fractional_offset_samples) % period
        start = int(native.probe_index) * self.half_window
        return ToneGuidedObservation(
            receiver=receiver,
            probe_index=int(native.probe_index),
            probe_start_sample=start,
            local_epoch_sample=local,
            dwell_epoch_sample=start + local,
            acquired_cfo_hz=float(native.scored_cfo_hz),
            tracking_cfo_hz=float(native.tracking_cfo_hz),
            margin=float(native.margin),
            fractional_complete=bool(native.fractional_complete),
            supported=bool(native.valid_support),
            fitted=False,
            candidate_index=0,
            exact_score=float(native.exact_score),
            control_score=float(native.control_score),
            support_frames=int(native.support_frames),
            valid_bounds=bool(native.valid_bounds),
            status=int(native.status),
            total_cpu_ms=float(native.total_cpu_ms),
            total_wall_ms=float(native.total_wall_ms),
            expected_physical_cfo_hz=float(native.expected_physical_cfo_hz),
            cfo_residual_from_scored_hz=float(native.cfo_residual_from_scored_hz),
            physical_cfo_innovation_hz=float(native.physical_cfo_innovation_hz),
            nuisance_enabled=bool(native.nuisance.enabled),
            nuisance_applied=bool(native.nuisance.applied),
            nuisance_frequency_hz=float(native.nuisance.frequency_hz),
            nuisance_spectral_fraction=float(native.nuisance.spectral_fraction),
            nuisance_fitted_power_fraction=float(native.nuisance.fitted_power_fraction),
            nuisance_cpu_ms=float(native.nuisance_cpu_ms),
            pack_cpu_ms=float(native.pack_cpu_ms),
            conversion_cpu_ms=float(native.conversion_cpu_ms),
            glrt_cpu_ms=float(native.glrt_cpu_ms),
            glrt_evaluations=int(native.glrt_evaluations),
            coarse_search_evaluations=int(native.coarse_search_evaluations),
            fine_search_evaluations=int(native.fine_search_evaluations),
            conditioned_search_evaluations=int(native.conditioned_search_evaluations),
            epoch_lattice_evaluations=int(native.epoch_lattice_evaluations),
        )

    def guided_components(
        self,
        raw,
        *,
        receiver: int,
        probe_index: int,
        epoch_sample: int,
        fractional_offset_samples: float,
        scoring_cfo_hz: float,
        expected_physical_cfo_hz: float,
    ) -> ToneGuidedObservation | None:
        values = self._raw(raw, receiver)
        if (
            type(probe_index) is not int or not 0 <= probe_index < 11
            or type(epoch_sample) is not int or not 0 <= epoch_sample < round(self.rate / 750)
            or not math.isfinite(float(fractional_offset_samples))
            or abs(float(fractional_offset_samples)) > 2
            or not math.isfinite(float(scoring_cfo_hz))
            or not math.isfinite(float(expected_physical_cfo_hz))
        ):
            raise ValueError("invalid tone-guided point")
        native = _ResultNative()
        status = self.library.leo_tone_guided_probe_ci16(
            self.workspace,
            values.ctypes.data_as(ct.c_void_p),
            len(values),
            receiver,
            probe_index,
            epoch_sample,
            float(fractional_offset_samples),
            float(scoring_cfo_hz),
            float(expected_physical_cfo_hz),
            ct.byref(native),
        )
        if status:
            return None
        result = self._observation(native, receiver)
        if (
            result.probe_index != probe_index
            or result.acquired_cfo_hz != float(scoring_cfo_hz)
            or result.expected_physical_cfo_hz != float(expected_physical_cfo_hz)
        ):
            raise ValueError("tone-guided result changed caller identity")
        return result

    def guided(
        self,
        raw,
        *,
        receiver: int,
        probe_index: int,
        predicted_local_epoch_sample: float,
        scoring_cfo_hz: float,
        expected_physical_cfo_hz: float,
    ) -> ToneGuidedObservation | None:
        if not math.isfinite(float(predicted_local_epoch_sample)):
            raise ValueError("finite predicted local epoch required")
        period = self.rate / FRAME_RATE_HZ
        phase = math.fmod(float(predicted_local_epoch_sample), period)
        if phase < 0:
            phase += period
        center = math.floor(phase + 0.5)
        fractional = phase - center
        if center >= round(self.rate / 750):
            center = 0
            fractional = phase - period
        return self.guided_components(
            raw,
            receiver=receiver,
            probe_index=probe_index,
            epoch_sample=center,
            fractional_offset_samples=fractional,
            scoring_cfo_hz=scoring_cfo_hz,
            expected_physical_cfo_hz=expected_physical_cfo_hz,
        )


__all__ = [
    "NativeToneGuided", "SUPPORT_GUARD_HZ", "ToneGuidedObservation",
    "build_library", "verify_library",
]
