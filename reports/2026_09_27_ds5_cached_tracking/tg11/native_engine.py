"""Pure, stateless-facing TG11-v1 native observation engine."""

from __future__ import annotations

import ctypes as ct
import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
RESEARCH_NATIVE = REPORT / "native"
FFT32 = REPORT / "fft32"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
DEPLOY_NATIVE = DEPLOY / "src/leo/analysis/native_presence"
sys.path[:0] = [str(DEPLOY), str(DEPLOY / "src"), str(RESEARCH_NATIVE)]

from leo.analysis.starlink.templates import qin_edge_pilot_frame  # noqa: E402
from tools.native_presence import array, pointer  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class ScreenWindow:
    probe_index: int
    probe_start_sample: int
    projected_epoch_sample: float
    score: float


@dataclass(frozen=True)
class ScreenResult:
    receiver: int
    windows: tuple[ScreenWindow, ...]
    selected_projection: int
    projection_contrast: tuple[float, float]
    fold_cpu_ms: float
    correlation_cpu_ms: float
    total_cpu_ms: float
    total_wall_ms: float
    _engine_token: int
    _raw_address: int


@dataclass(frozen=True)
class Observation:
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
    candidate_index: int = 0
    exact_score: float = 0.0
    control_score: float = 0.0
    support_frames: int = 0
    valid_bounds: bool = False
    status: int = 0
    total_cpu_ms: float = 0.0
    total_wall_ms: float = 0.0


class _ScreenNative(ct.Structure):
    _fields_ = [
        ("probe_count", ct.c_uint32), ("selected_projection", ct.c_uint32),
        ("probe_start_samples", ct.c_uint32 * 11),
        ("projected_epoch_samples", ct.c_uint32 * 11),
        ("scores", ct.c_double * 11),
        ("projection_scores", (ct.c_double * 11) * 2),
        ("projection_epochs", (ct.c_uint32 * 11) * 2),
        ("projection_contrast", ct.c_double * 2),
        ("fold_cpu_ms", ct.c_double), ("correlation_cpu_ms", ct.c_double),
        ("total_cpu_ms", ct.c_double), ("total_wall_ms", ct.c_double),
    ]


class _ObservationNative(ct.Structure):
    _fields_ = [
        ("probe_index", ct.c_uint32), ("candidate_index", ct.c_uint32),
        ("support_frames", ct.c_uint32), ("valid_support", ct.c_uint32),
        ("fitted", ct.c_uint32), ("fractional_complete", ct.c_uint32),
        ("valid_bounds", ct.c_uint32), ("status", ct.c_uint32),
        ("epoch", ct.c_int32), ("fractional_offset_samples", ct.c_double),
        ("acquired_cfo_hz", ct.c_double), ("tracking_cfo_hz", ct.c_double),
        ("exact_score", ct.c_double), ("control_score", ct.c_double),
        ("margin", ct.c_double), ("total_cpu_ms", ct.c_double),
        ("total_wall_ms", ct.c_double),
    ]


def build_library(output: Path = HERE / "libtg11.so") -> Path:
    output = output.resolve()
    receipt_path = output.with_name(output.name + ".build.json")
    own = [HERE / name for name in ("tg11_native.c", "tg11_native.h", "native_engine.py")]
    frozen = [RESEARCH_NATIVE / name for name in (
        "known_state.c", "known_state.h", "known_state_v2.c", "known_state_v2.h",
        "known_state_v3.c", "known_state_v3.h", "blind_strided_v4.c",
        "blind_strided_v4.h", "profile.json",
    )]
    dependencies = sorted(DEPLOY_NATIVE.glob("*.[ch]")) + [
        DEPLOY / "src/leo/analysis/starlink/_native_acquisition_grid.inc",
        FFT32 / "fft32_fftw.c", Path("/usr/include/fftw3.h"),
        Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3").resolve(),
    ]
    sources = own + frozen + dependencies
    hashes = {str(path.resolve()): sha256(path) for path in sources}
    if output.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt["sources_sha256"] != hashes or receipt["binary_sha256"] != sha256(output):
            raise ValueError("TG11 binary or source differs from build receipt")
        return output
    if output.exists() or receipt_path.exists():
        raise ValueError("partial TG11 build")
    compiler = shutil.which("cc")
    if compiler is None:
        raise FileNotFoundError("cc")
    profile = json.loads((RESEARCH_NATIVE / "profile.json").read_text())
    fftw = str(Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3").resolve())
    command = [
        compiler, "-std=c11", "-O3", "-fno-math-errno", "-Wall", "-Wextra",
        "-Werror", *profile["flags"], "-shared", "-fPIC", "-I", str(HERE),
        "-I", str(RESEARCH_NATIVE), "-I", str(DEPLOY_NATIVE),
        str(HERE / "tg11_native.c"), str(FFT32 / "fft32_fftw.c"), fftw,
        "-lm", "-o", str(output),
    ]
    subprocess.run(command, check=True)
    if hashes != {str(path.resolve()): sha256(path) for path in sources}:
        output.unlink(missing_ok=True)
        raise ValueError("TG11 source changed during build")
    receipt = {
        "schema": "org.leo.research.tg11-native-build/v1",
        "created_unix_ns": time.time_ns(), "command": command,
        "compiler_sha256": sha256(Path(compiler).resolve()),
        "compiler_version": subprocess.run(
            [compiler, "--version"], check=True, text=True, capture_output=True
        ).stdout,
        "sources_sha256": hashes, "binary_sha256": sha256(output),
        "fft_backend": "FFTW FP32; rank projection uses frozen FP32 rank implementation",
        "profile_sha256": sha256(RESEARCH_NATIVE / "profile.json"),
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return output


class NativeTG11:
    def __init__(self, rate: int, edge: str, library: Path | None = None, *, bins: int = 512):
        if (type(rate) is not int or rate not in (2_500_000, 5_000_000)
                or edge not in ("lower", "upper") or type(bins) is not int
                or bins not in (512, 1024, 2048, 4096, 8192)):
            raise ValueError("unsupported TG11 geometry")
        self.rate = rate
        self.window = rate // 50
        self.half_window = rate // 100
        self.library = ct.CDLL(str(build_library() if library is None else library))
        lib = self.library
        lib.leo_tg11_create.argtypes = [
            ct.c_uint32, ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_uint32,
        ]
        lib.leo_tg11_create.restype = ct.c_void_p
        lib.leo_tg11_destroy.argtypes = [ct.c_void_p]
        lib.leo_tg11_screen_ci16.argtypes = [
            ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.POINTER(_ScreenNative),
        ]
        lib.leo_tg11_screen_ci16.restype = ct.c_int
        lib.leo_tg11_blind_probe_ci16.argtypes = [
            ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.c_uint32,
            ct.POINTER(_ObservationNative), ct.POINTER(ct.c_uint32),
        ]
        lib.leo_tg11_blind_probe_ci16.restype = ct.c_int
        lib.leo_tg11_guided_probe_ci16.argtypes = [
            ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.c_uint32,
            ct.c_double, ct.c_double, ct.c_double, ct.POINTER(_ObservationNative),
        ]
        lib.leo_tg11_guided_probe_ci16.restype = ct.c_int
        exact, control = [array(qin_edge_pilot_frame(rate, edge, symbol_roll=roll))
                          for roll in (0, 17)]
        self.workspace = lib.leo_tg11_create(
            rate, pointer(exact), pointer(control), len(exact), bins
        )
        if not self.workspace:
            raise ValueError("TG11 initialization failed")
        self._token = 0
        self._last_screen: dict[int, ScreenResult] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        if self.workspace:
            self.library.leo_tg11_destroy(self.workspace)
            self.workspace = None
            self._last_screen.clear()

    def _raw(self, raw, receiver: int) -> np.ndarray:
        values = np.asarray(raw)
        if (not self.workspace or values.dtype != np.dtype("int16")
                or values.shape != (self.rate * 120 // 1000, 2, 2)
                or not values.flags.c_contiguous or type(receiver) is not int
                or receiver not in (0, 1)):
            raise ValueError("complete C-contiguous natural dual-RX CI16 dwell required")
        return values

    def screen(self, raw, *, receiver: int) -> ScreenResult:
        values = self._raw(raw, receiver)
        native = _ScreenNative()
        if self.library.leo_tg11_screen_ci16(
            self.workspace, values.ctypes.data_as(ct.c_void_p), len(values), receiver,
            ct.byref(native),
        ):
            raise ValueError("TG11 screen rejected input")
        if native.probe_count != 11 or native.selected_projection not in (0, 1):
            raise ValueError("invalid TG11 screen ABI result")
        finite = [*native.scores, *native.projection_contrast,
                  native.fold_cpu_ms, native.correlation_cpu_ms,
                  native.total_cpu_ms, native.total_wall_ms]
        if not all(math.isfinite(value) and value >= 0 for value in finite):
            raise ValueError("non-finite TG11 screen result")
        expected_starts = tuple(index * self.half_window for index in range(11))
        if tuple(native.probe_start_samples) != expected_starts:
            raise ValueError("invalid TG11 probe coordinates")
        self._token += 1
        result = ScreenResult(
            receiver=receiver,
            windows=tuple(ScreenWindow(index, expected_starts[index],
                float(native.projected_epoch_samples[index]), float(native.scores[index]))
                for index in range(11)),
            selected_projection=int(native.selected_projection),
            projection_contrast=tuple(float(value) for value in native.projection_contrast),
            fold_cpu_ms=float(native.fold_cpu_ms),
            correlation_cpu_ms=float(native.correlation_cpu_ms),
            total_cpu_ms=float(native.total_cpu_ms), total_wall_ms=float(native.total_wall_ms),
            _engine_token=self._token, _raw_address=values.ctypes.data,
        )
        self._last_screen[receiver] = result
        return result

    def _observation(self, native: _ObservationNative, receiver: int) -> Observation:
        if (native.probe_index >= 11 or native.candidate_index >= 2
                or native.support_frames > 16 or native.valid_support not in (0, 1)
                or native.fitted not in (0, 1) or native.fractional_complete not in (0, 1)
                or native.valid_bounds not in (0, 1)):
            raise ValueError("invalid TG11 observation ABI result")
        floats = [native.fractional_offset_samples, native.acquired_cfo_hz,
                  native.tracking_cfo_hz, native.exact_score, native.control_score,
                  native.margin, native.total_cpu_ms, native.total_wall_ms]
        if not all(math.isfinite(value) for value in floats):
            raise ValueError("non-finite TG11 observation")
        local = (native.epoch + native.fractional_offset_samples) % (self.rate / 750.0)
        start = int(native.probe_index) * self.half_window
        return Observation(
            receiver=receiver, probe_index=int(native.probe_index),
            probe_start_sample=start, local_epoch_sample=local,
            dwell_epoch_sample=start + local,
            acquired_cfo_hz=float(native.acquired_cfo_hz),
            tracking_cfo_hz=float(native.tracking_cfo_hz), margin=float(native.margin),
            fractional_complete=bool(native.fractional_complete),
            supported=bool(native.valid_support), fitted=bool(native.fitted),
            candidate_index=int(native.candidate_index),
            exact_score=float(native.exact_score), control_score=float(native.control_score),
            support_frames=int(native.support_frames), valid_bounds=bool(native.valid_bounds),
            status=int(native.status), total_cpu_ms=float(native.total_cpu_ms),
            total_wall_ms=float(native.total_wall_ms),
        )

    def blind(self, raw, *, receiver: int, screen: ScreenResult) -> tuple[Observation, ...]:
        values = self._raw(raw, receiver)
        if (screen is not self._last_screen.get(receiver)
                or screen.receiver != receiver or screen._raw_address != values.ctypes.data):
            raise ValueError("blind confirmation requires this engine's existing screen")
        observations: list[Observation] = []
        for probe in range(11):
            native = (_ObservationNative * 2)()
            count = ct.c_uint32()
            if self.library.leo_tg11_blind_probe_ci16(
                self.workspace, values.ctypes.data_as(ct.c_void_p), len(values), receiver,
                probe, native, ct.byref(count),
            ) or count.value > 2:
                raise ValueError("TG11 blind confirmation failed")
            observations.extend(self._observation(native[index], receiver)
                                for index in range(count.value))
        return tuple(observations)

    def guided(self, raw, *, receiver: int, probe_index: int,
               predicted_local_epoch_sample: float, scoring_cfo_hz: float,
               expected_physical_cfo_hz: float | None = None) -> Observation | None:
        values = self._raw(raw, receiver)
        if (type(probe_index) is not int or not 0 <= probe_index < 11
                or not math.isfinite(float(predicted_local_epoch_sample))
                or not math.isfinite(float(scoring_cfo_hz))):
            raise ValueError("finite guided state and a valid probe are required")
        expected = scoring_cfo_hz if expected_physical_cfo_hz is None else expected_physical_cfo_hz
        if not math.isfinite(float(expected)):
            raise ValueError("finite expected physical CFO required")
        native = _ObservationNative()
        if self.library.leo_tg11_guided_probe_ci16(
            self.workspace, values.ctypes.data_as(ct.c_void_p), len(values), receiver,
            probe_index, float(predicted_local_epoch_sample), float(scoring_cfo_hz),
            float(expected), ct.byref(native),
        ):
            return None
        return self._observation(native, receiver)


__all__ = ["NativeTG11", "Observation", "ScreenResult", "ScreenWindow", "build_library"]

