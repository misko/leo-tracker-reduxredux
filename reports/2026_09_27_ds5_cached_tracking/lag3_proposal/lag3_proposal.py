"""Frozen ctypes port for the isolated lag-3 proposal feasibility test."""

from __future__ import annotations

import ctypes as ct
import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
if str(DEPLOY / "src") not in sys.path:
    sys.path.insert(0, str(DEPLOY / "src"))
from leo.analysis.starlink.templates import qin_edge_pilot_frame  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class Complex(ct.Structure):
    _fields_ = [("re", ct.c_double), ("im", ct.c_double)]


class Candidate(ct.Structure):
    _fields_ = [
        ("window", ct.c_uint32), ("integer_epoch", ct.c_uint32),
        ("projected_bin", ct.c_uint32), ("phase_valid", ct.c_uint32),
        ("in_declared_cfo_range", ct.c_uint32), ("supported", ct.c_uint32),
        ("reserved", ct.c_uint32), ("phase_cfo_hz", ct.c_double),
        ("proposal_score", ct.c_double), ("phase_support_score", ct.c_double),
        ("correlation_re", ct.c_double), ("correlation_im", ct.c_double),
    ]


class Result(ct.Structure):
    _fields_ = [
        ("candidates", Candidate * 3), ("candidate_count", ct.c_uint32),
        ("lag_samples", ct.c_uint32), ("bins", ct.c_uint32),
        ("reserved", ct.c_uint32), ("fold_cpu_ms", ct.c_double),
        ("correlation_cpu_ms", ct.c_double), ("total_cpu_ms", ct.c_double),
        ("total_wall_ms", ct.c_double),
    ]


def build_library(output: Path = HERE / "liblag3_proposal.so") -> Path:
    output = output.resolve()
    receipt_path = output.with_name(output.name + ".build.json")
    sources = [HERE / name for name in ("lag3_proposal.c", "lag3_proposal.h", "lag3_proposal.py", "design.json")]
    hashes = {str(path.resolve()): sha256(path) for path in sources}
    if output.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if sha256(output) != receipt["binary_sha256"] or hashes != receipt["sources_sha256"]:
            raise ValueError("lag3 binary or frozen source does not match its build receipt")
        return output
    if output.exists() or receipt_path.exists():
        raise ValueError("partial lag3 build")
    compiler = shutil.which("cc")
    if compiler is None:
        raise FileNotFoundError("cc")
    command = [compiler, "-std=c11", "-O3", "-fno-math-errno", "-Wall", "-Wextra", "-Werror",
               "-shared", "-fPIC", str(HERE / "lag3_proposal.c"), "-lm", "-o", str(output)]
    subprocess.run(command, check=True)
    if hashes != {str(path.resolve()): sha256(path) for path in sources}:
        output.unlink(missing_ok=True)
        raise ValueError("lag3 source changed during build")
    receipt = {
        "schema": "org.leo.research.lag3-proposal-build/v1",
        "created_unix_ns": time.time_ns(), "command": command,
        "compiler_sha256": sha256(Path(compiler).resolve()),
        "compiler_version": subprocess.run([compiler, "--version"], check=True, text=True,
                                             capture_output=True).stdout,
        "sources_sha256": hashes, "binary_sha256": sha256(output),
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return output


class Lag3Proposal:
    """One rate/edge workspace. Calls accept only sample-aligned dual-RX CI16."""

    def __init__(self, rate_hz: int, edge: str, library: Path | None = None):
        self.rate_hz = int(rate_hz)
        self.edge = str(edge)
        self.template = np.asarray(qin_edge_pilot_frame(self.rate_hz, self.edge), dtype=np.complex128)
        self.template_sha256 = hashlib.sha256(self.template.astype("<c16", copy=False).tobytes()).hexdigest()
        self.library_path = (library or build_library()).resolve()
        self.library = ct.CDLL(str(self.library_path))
        self.library.leo_lag3_create.argtypes = [ct.c_uint32, ct.POINTER(Complex), ct.c_size_t]
        self.library.leo_lag3_create.restype = ct.c_void_p
        self.library.leo_lag3_destroy.argtypes = [ct.c_void_p]
        self.library.leo_lag3_run.argtypes = [ct.c_void_p, ct.POINTER(ct.c_int16), ct.c_size_t,
                                               ct.c_uint32, ct.POINTER(Result)]
        self.library.leo_lag3_run.restype = ct.c_int
        pair = np.empty((self.template.size, 2), dtype=np.float64)
        pair[:, 0] = self.template.real
        pair[:, 1] = self.template.imag
        self._template_pairs = pair
        self.workspace = self.library.leo_lag3_create(
            self.rate_hz, pair.ctypes.data_as(ct.POINTER(Complex)), pair.shape[0]
        )
        if not self.workspace:
            raise ValueError("native lag3 workspace creation failed")

    def close(self) -> None:
        if getattr(self, "workspace", None):
            self.library.leo_lag3_destroy(self.workspace)
            self.workspace = None

    def __del__(self):
        self.close()

    def run(self, raw: np.ndarray, receiver: int) -> dict:
        if not isinstance(raw, np.ndarray) or raw.dtype != np.dtype("<i2"):
            raise TypeError("raw must be a little-endian int16 numpy array")
        expected = self.rate_hz * 120 // 1000
        if raw.shape != (expected, 2, 2) or not raw.flags.c_contiguous:
            raise ValueError(f"raw must be C-contiguous with shape ({expected},2,2)")
        if receiver not in (0, 1):
            raise ValueError("receiver must be 0 or 1")
        result = Result()
        status = self.library.leo_lag3_run(
            self.workspace, raw.ctypes.data_as(ct.POINTER(ct.c_int16)), raw.shape[0],
            receiver, ct.byref(result)
        )
        if status:
            raise RuntimeError(f"native lag3 run failed: {status}")
        if result.candidate_count > 3 or result.lag_samples != 3 or result.bins != 512 or result.reserved != 0:
            raise RuntimeError("native lag3 result ABI invariant failed")
        timings = (result.fold_cpu_ms, result.correlation_cpu_ms,
                   result.total_cpu_ms, result.total_wall_ms)
        if any(not math.isfinite(value) or value < 0.0 for value in timings):
            raise RuntimeError("native lag3 returned invalid timing")
        candidates = []
        for item in result.candidates[: result.candidate_count]:
            flags = (item.phase_valid, item.in_declared_cfo_range, item.supported)
            values = (item.phase_cfo_hz, item.proposal_score, item.phase_support_score,
                      item.correlation_re, item.correlation_im)
            n = self.template.size
            if (item.reserved != 0 or any(flag not in (0, 1) for flag in flags) or
                    item.window >= 6 or item.projected_bin >= 512 or item.integer_epoch >= n or
                    any(not math.isfinite(value) for value in values) or
                    item.proposal_score < 0.0 or not 0.0 <= item.phase_support_score <= 1.000001 or
                    abs(item.phase_cfo_hz) > self.rate_hz / 6 + 1e-6 or
                    (item.supported and not (item.phase_valid and item.in_declared_cfo_range))):
                raise RuntimeError("native lag3 candidate invariant failed")
            candidates.append({
                "window": int(item.window), "epoch_samples": int(item.integer_epoch),
                "projected_bin": int(item.projected_bin), "cfo_hz": float(item.phase_cfo_hz),
                "score": float(item.proposal_score),
                "phase_support_score": float(item.phase_support_score),
                "correlation_re": float(item.correlation_re),
                "correlation_im": float(item.correlation_im),
                "phase_valid": bool(item.phase_valid),
                "in_declared_cfo_range": bool(item.in_declared_cfo_range),
                "supported": bool(item.supported),
            })
        return {
            "rate_hz": self.rate_hz, "edge": self.edge, "receiver": receiver,
            "epoch_period_samples": int(self.template.size),
            "epoch_semantics": "integer modulo nearbyint(rate_hz/750), refined in a frozen local 1-D native-cell scan",
            "cfo_semantics": "principal direct lag3 phase in [-rate_hz/6,+rate_hz/6]",
            "lag_samples": int(result.lag_samples), "bins": int(result.bins),
            "candidates": candidates,
            "native_timing_ms": {"fold_cpu": result.fold_cpu_ms,
                                 "correlation_cpu": result.correlation_cpu_ms,
                                 "total_cpu": result.total_cpu_ms, "total_wall": result.total_wall_ms},
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
