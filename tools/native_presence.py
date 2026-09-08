"""Development-only native GLRT bindings/build helpers; never a radio dependency."""

from __future__ import annotations

import ctypes as ct
import hashlib
import json
import shutil
import struct
import subprocess
import time
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "src/leo/analysis/native_presence"


def build_scanner_glrt_port(
    output: Path, *, compiler: str = "cc", cflags: tuple[str, ...] = ()
) -> Path:
    """Build the acquisition-facing port, without linking numerical code/IIO.

    This is a development/build-host helper only. A daemon consumes the built
    library and scanner_glrt.h, not another component's private Python modules.
    """
    output = output.resolve()
    receipt = output.with_name(output.name + ".build.json")
    for path in (output, receipt):
        if path.exists():
            raise FileExistsError(path)
    source = ROOT / "src/leo/scanner/native_presence"
    names = (
        "scanner_glrt.c",
        "scanner_glrt_request.c",
        "pool.c",
        "frame_codec.c",
        "frame_result.c",
    )
    sources = [source / name for name in names]
    sources += [
        source / name for name in ("scanner_glrt.h", "pool.h", "frame_codec.h", "frame_result.h")
    ]
    sources += [NATIVE / "presence.h", NATIVE / "window_rank.h", Path(__file__)]
    hashes = {str(path.relative_to(ROOT)): _digest(path) for path in sources}
    compiler_path = shutil.which(compiler)
    if compiler_path is None:
        raise FileNotFoundError(compiler)
    command = [
        compiler_path,
        "-std=c11",
        "-O3",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-shared",
        "-fPIC",
        *cflags,
        *(str(source / name) for name in names),
        "-pthread",
        "-lm",
        "-o",
        str(output),
    ]
    subprocess.run(command, check=True)
    if hashes != {str(path.relative_to(ROOT)): _digest(path) for path in sources}:
        raise RuntimeError("source changed during SDK build")
    with receipt.open("x") as stream:
        json.dump(
            {
                "schema": "org.leo.research.scanner-glrt-port-build/v1",
                "created_unix_ns": time.time_ns(),
                "command": command,
                "compiler_version": subprocess.run(
                    [compiler_path, "--version"], check=True, text=True, capture_output=True
                ).stdout,
                "compiler_sha256": _digest(Path(compiler_path).resolve()),
                "sources_sha256": hashes,
                "binary_sha256": _digest(output),
            },
            stream,
            indent=2,
        )
        stream.write("\n")
    return output


class Candidate(ct.Structure):
    _fields_ = [
        ("epoch", ct.c_int32),
        ("fractional_complete", ct.c_int32),
        *[
            (name, ct.c_double)
            for name in (
                "acquired_cfo_hz",
                "fractional_offset_samples",
                "tracking_cfo_hz",
                "exact_score",
                "control_score",
                "margin",
                "acquire_score",
                "verify_score",
                "verify_control_score",
                "conditioned_score",
                "coarse_score",
            )
        ],
        ("exact_grid", ct.c_double * 5),
        ("control_grid", ct.c_double * 5),
    ]


class Result(ct.Structure):
    _fields_ = [
        ("candidate_count", ct.c_int32),
        ("candidates", Candidate * 2),
        *[
            (name, ct.c_double)
            for name in (
                "conversion_cpu_ms",
                "coarse_cpu_ms",
                "fine_cpu_ms",
                "fractional_cpu_ms",
                "total_cpu_ms",
                "total_wall_ms",
            )
        ],
    ]


class Profile(ct.Structure):
    _fields_ = [
        *[
            (name, ct.c_double)
            for name in (
                "acquisition_fft_cpu_ms",
                "conditioned_cpu_ms",
                "verification_cpu_ms",
                "epoch_lattice_cpu_ms",
                "final_confirmation_cpu_ms",
                "local_coarse_cpu_ms",
            )
        ],
        *[
            (name, ct.c_uint32)
            for name in (
                "coarse_frames",
                "fine_frames",
                "epoch_frames",
                "anchor_stride",
                "epoch_stride",
                "conditioned_radius_hz",
            )
        ],
    ]


class Nuisance(ct.Structure):
    _fields_ = [("enabled", ct.c_int32), ("applied", ct.c_int32)] + [
        (name, ct.c_double)
        for name in ("frequency_hz", "spectral_fraction", "fitted_power_fraction", "cpu_ms")
    ]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build(
    output: Path,
    compiler: str,
    flags: tuple[str, ...],
    *,
    executable: bool,
    scanner_worker: bool = False,
    window_ranker: bool = False,
    dwell_presence: bool = False,
    ldflags: tuple[str, ...] = (),
    dependencies: tuple[Path, ...] = (),
) -> Path:
    output = output.resolve()
    receipt = output.with_name(output.name + ".build.json")
    for path in (output, receipt):
        if path.exists():
            raise FileExistsError(path)
    compiler_path = shutil.which(compiler)
    if compiler_path is None:
        raise FileNotFoundError(compiler)
    sources = sorted(NATIVE.glob("*.[ch]"))
    sources += [ROOT / "src/leo/analysis/starlink/_native_acquisition_grid.inc", Path(__file__)]
    entry = ROOT / "tools/native_presence_replay.c"
    worker_sources = []
    if scanner_worker:
        entry = ROOT / "src/leo/scanner/native_presence/worker.c"
        worker_sources = [ROOT / "src/leo/scanner/native_presence/pool.c"]
        sources += sorted((ROOT / "src/leo/scanner/native_presence").glob("*.[ch]"))
    elif window_ranker:
        entry = ROOT / "tools/presence_window_rank_replay.c"
        if executable:
            sources += [entry]
    elif dwell_presence:
        entry = ROOT / "tools/presence_dwell_replay.c"
        if executable:
            sources += [entry]
    elif executable:
        sources += [entry]
    hashes = {str(path.relative_to(ROOT)): _digest(path) for path in sources}
    dependency_hashes = {str(path.resolve()): _digest(path) for path in dependencies}
    command = [
        compiler_path,
        "-std=c11",
        "-O3",
        "-fno-math-errno",
        "-Wall",
        "-Wextra",
        "-Werror",
        *flags,
        *([str(entry), *(str(p) for p in worker_sources)] if executable else []),
        *(
            [str(NATIVE / "window_rank.c")]
            if window_ranker
            else [str(NATIVE / "presence.c"), str(NATIVE / "fft.c")]
        ),
        *(
            [str(NATIVE / "window_rank.c"), str(NATIVE / "dwell.c")]
            if dwell_presence or scanner_worker
            else []
        ),
        *ldflags,
        "-lm",
        "-o",
        str(output),
    ]
    subprocess.run(command, check=True)
    if hashes != {str(path.relative_to(ROOT)): _digest(path) for path in sources}:
        raise RuntimeError("source changed during build; artifact is not qualified")
    if dependency_hashes != {str(path.resolve()): _digest(path) for path in dependencies}:
        raise RuntimeError("dependency changed during build; artifact is not qualified")
    compiler_version = subprocess.run(
        [compiler_path, "--version"], check=True, text=True, capture_output=True
    ).stdout
    with receipt.open("x") as stream:
        json.dump(
            {
                "schema": "org.leo.research.native-presence-build/v1",
                "created_unix_ns": time.time_ns(),
                "command": command,
                "compiler_version": compiler_version,
                "compiler_sha256": _digest(Path(compiler_path).resolve()),
                "sources_sha256": hashes,
                "dependencies_sha256": dependency_hashes,
                "binary_sha256": _digest(output),
            },
            stream,
            indent=2,
        )
        stream.write("\n")
    return output


def build_library(
    output: Path,
    *,
    compiler: str = "cc",
    cflags: tuple[str, ...] = (),
    ldflags: tuple[str, ...] = (),
    dependencies: tuple[Path, ...] = (),
) -> Path:
    return _build(
        output,
        compiler,
        ("-shared", "-fPIC", *cflags),
        executable=False,
        ldflags=ldflags,
        dependencies=dependencies,
    )


def build_executable(
    output: Path,
    *,
    compiler: str = "cc",
    sanitize: bool = False,
    cflags: tuple[str, ...] = (),
    ldflags: tuple[str, ...] = (),
    dependencies: tuple[Path, ...] = (),
) -> Path:
    sanitizers = ("-fsanitize=address,undefined", "-fno-omit-frame-pointer") if sanitize else ()
    return _build(
        output,
        compiler,
        (*sanitizers, *cflags),
        executable=True,
        ldflags=ldflags,
        dependencies=dependencies,
    )


def build_worker(
    output: Path,
    *,
    compiler: str = "cc",
    cflags: tuple[str, ...] = (),
    ldflags: tuple[str, ...] = (),
    dependencies: tuple[Path, ...] = (),
) -> Path:
    """Build the isolated scanner consumer, separate from the numerical library."""
    return _build(
        output,
        compiler,
        cflags,
        executable=True,
        scanner_worker=True,
        ldflags=ldflags,
        dependencies=dependencies,
    )


def build_window_ranker(
    output: Path, *, compiler: str = "cc", executable: bool = False, cflags: tuple[str, ...] = ()
) -> Path:
    flags = () if executable else ("-shared", "-fPIC")
    return _build(output, compiler, (*flags, *cflags), executable=executable, window_ranker=True)


def build_dwell_presence(
    output: Path,
    *,
    compiler: str = "cc",
    executable: bool = False,
    cflags: tuple[str, ...] = (),
    ldflags: tuple[str, ...] = (),
    dependencies: tuple[Path, ...] = (),
) -> Path:
    flags = () if executable else ("-shared", "-fPIC")
    return _build(
        output,
        compiler,
        (*flags, *cflags),
        executable=executable,
        dwell_presence=True,
        ldflags=ldflags,
        dependencies=dependencies,
    )


def write_templates(path: Path, rate: int):
    """Package both edge templates for a read-only inherited worker descriptor."""
    if rate not in (2500000, 5000000):
        raise ValueError("unqualified template rate")
    n = round(rate / 750)
    with path.open("xb") as output:
        output.write(struct.pack("<4sII", b"LPT1", rate, n))
        for edge in ("lower", "upper"):
            for roll in (0, 17):
                values = np.asarray(
                    qin_edge_pilot_frame(rate, edge, symbol_roll=roll), dtype="<c16"
                )
                output.write(values.tobytes())


def write_probe(path: Path, values, rate: int, edge: str, counter: int = 0, *, ci16: bool = False):
    """Explicit little-endian replay format; generated test data, never archive writes."""
    samples = np.asarray(values, dtype="<c16")
    if samples.shape != (rate // 50,) or rate not in (2_500_000, 5_000_000):
        raise ValueError("exactly 20 ms at a qualified sample rate required")
    if edge not in ("lower", "upper") or not 0 <= counter < 2**64:
        raise ValueError("invalid edge or counter")
    payload = samples
    if ci16:
        components = np.column_stack((samples.real, samples.imag))
        if (
            not np.all(np.isfinite(components))
            or np.any(components < -32768)
            or np.any(components > 32767)
            or np.any(components != np.rint(components))
        ):
            raise ValueError("CI16 replay requires exactly representable integer samples")
        payload = components.astype("<i2")
    with path.open("xb") as stream:
        stream.write(
            struct.pack(
                "<4sIIIIQ",
                b"LPR1",
                rate,
                int(edge == "upper"),
                len(samples),
                2 if ci16 else 1,
                counter,
            )
        )
        for roll in (0, 17):
            stream.write(
                np.asarray(
                    qin_edge_pilot_frame(rate, edge, symbol_roll=roll), dtype="<c16"
                ).tobytes()
            )
        stream.write(payload.tobytes())


def array(values):
    return np.ascontiguousarray(values, dtype=np.complex128)


def pointer(values):
    return values.ctypes.data_as(ct.c_void_p)


class NativePresence:
    """Own one non-reentrant workspace for one rate and edge."""

    def __init__(self, library: Path, rate: int, edge: str):
        self.rate = rate
        self.library = ct.CDLL(str(library))
        self.library.leo_presence_create.argtypes = [
            ct.c_uint32,
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
        ]
        self.library.leo_presence_create.restype = ct.c_void_p
        self.library.leo_presence_destroy.argtypes = [ct.c_void_p]
        self.library.leo_presence_destroy.restype = None
        self.library.leo_presence_get_profile.argtypes = [ct.c_void_p, ct.POINTER(Profile)]
        self._has_nuisance = hasattr(self.library, "leo_presence_get_nuisance")
        if self._has_nuisance:
            self.library.leo_presence_get_nuisance.argtypes = [ct.c_void_p, ct.POINTER(Nuisance)]
        self.library.leo_presence_run.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
            ct.POINTER(Result),
        ]
        self.library.leo_presence_run_ci16.argtypes = self.library.leo_presence_run.argtypes
        self._has_confirmation = hasattr(self.library, "leo_presence_confirm_ci16")
        if self._has_confirmation:
            self.library.leo_presence_confirm_ci16.argtypes = [
                ct.c_void_p,
                ct.c_void_p,
                ct.c_size_t,
                ct.c_int32,
                ct.POINTER(Result),
            ]
            self.library.leo_presence_confirm_ci16.restype = ct.c_int
        self.library.leo_presence_coarse.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_void_p,
        ]
        self.library.leo_presence_glrt.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_int32,
            ct.c_double,
            ct.c_double,
            ct.c_void_p,
        ]
        exact = array(qin_edge_pilot_frame(rate, edge))
        control = array(qin_edge_pilot_frame(rate, edge, symbol_roll=17))
        self.workspace = self.library.leo_presence_create(
            rate, pointer(exact), pointer(control), len(exact)
        )
        if not self.workspace:
            raise ValueError("native presence initialization rejected the configuration")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.workspace:
            self.library.leo_presence_destroy(self.workspace)
            self.workspace = None

    def run(self, values):
        if not self.workspace:
            raise ValueError("native workspace is closed")
        samples = array(values)
        if samples.ndim != 1:
            raise ValueError("one RX vector required")
        result = Result()
        if self.library.leo_presence_run(
            self.workspace, pointer(samples), len(samples), ct.byref(result)
        ):
            raise ValueError("native presence rejected the input")
        return result

    def profile(self):
        result = Profile()
        if self.library.leo_presence_get_profile(self.workspace, ct.byref(result)):
            raise ValueError("native workspace is closed")
        return {name: getattr(result, name) for name, _ in Profile._fields_}

    def confirm(self, iq, epoch):
        if not self.workspace or not self._has_confirmation:
            raise ValueError("proposal confirmation unavailable")
        samples = np.asarray(iq)
        if (
            samples.dtype != np.dtype("int16")
            or samples.shape != (self.rate // 50, 2)
            or type(epoch) is not int
            or not 0 <= epoch < round(self.rate / 750)
        ):
            raise ValueError("one 20ms CI16 RX interval and local integer seed required")
        samples = np.ascontiguousarray(samples)
        result = Result()
        if self.library.leo_presence_confirm_ci16(
            self.workspace, pointer(samples), len(samples), epoch, ct.byref(result)
        ):
            raise ValueError("proposal confirmation rejected input")
        return result

    def nuisance(self):
        if not self._has_nuisance:
            raise ValueError("native library does not expose nuisance evidence")
        result = Nuisance()
        if self.library.leo_presence_get_nuisance(self.workspace, ct.byref(result)):
            raise ValueError("native workspace is closed")
        return {name: getattr(result, name) for name, _ in Nuisance._fields_}

    def coarse(self, values):
        samples = array(values)
        result = np.zeros((11, round(self.rate / 750)))
        if samples.ndim != 1 or self.library.leo_presence_coarse(
            self.workspace, pointer(samples), len(samples), pointer(result)
        ):
            raise ValueError("native coarse search rejected the input")
        return result

    def glrt(self, values, epoch, cfo, offset=0.0):
        samples = array(values)
        result = np.zeros(3)
        if samples.ndim != 1 or self.library.leo_presence_glrt(
            self.workspace, pointer(samples), len(samples), epoch, cfo, offset, pointer(result)
        ):
            raise ValueError("native GLRT rejected the input")
        return result
