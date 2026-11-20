"""Compact fixed-owner fit using an arrowhead Gram matrix and bounded Schur solves."""

import ctypes
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import robust_em as lean

SOURCE = Path(__file__).with_suffix(".c")
BUILD_FLAGS = ("-std=c11", "-O3", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror")


@dataclass(frozen=True)
class Statistics:
    gram: np.ndarray
    rhs: np.ndarray
    orbits: np.ndarray
    bounds: np.ndarray
    orbit_ids: tuple[int, ...]
    row_count: int
    weighted_energy: float


@dataclass(frozen=True)
class Solution:
    coefficients: np.ndarray
    position_covariance: np.ndarray
    optimality: float
    bound_updates: int


def _design(row, width):
    arc, winner = row.arc, row.winner
    track = arc.track
    # One local phase column and a right-hand side, independent of the orbit count.
    basis = np.zeros((len(track.t), width + 2))
    basis[:, :2] = arc.xy[winner]
    basis[:, 2 + track.lane] = 1000
    basis[:, 6 + track.lane] = 1000 * track.drift
    if width == 11:
        basis[:, 10] = 1000 * (track.rf / 1e9 - 11.5)
    basis[:, width] = arc.phase[winner]
    basis[:, width + 1] = arc.residual[winner] - row.alias * lean.PERIOD
    return basis


def _weight(row, length):
    return np.sqrt(min(1, 40 / length) / (1 + row.loss / 4))


def statistics(rows, half, arm):
    if arm not in lean.ARMS or not rows:
        raise ValueError("a fixed-owner fit needs tracks and a calibration arm")
    used = tuple(sorted({r.orbit for r in rows}))
    indexes = {sat: j for j, sat in enumerate(used)}
    width = 10 + int(arm == "fitted_c")
    sigma = np.r_[
        [1000.0] * 2, [lean.PERIOD / np.sqrt(12) / 1000] * 4, [1.5] * 4, [200.0] * (width - 10)
    ]
    bound = np.r_[
        [half] * 2,
        [lean.PERIOD / 1000] * 4,
        [6.0] * 4,
        [600.0] * (width - 10),
        [lean.PHASE_BOUND_S] * len(used),
    ]
    gram = np.diag(1 / sigma**2)
    rhs = np.zeros(width)
    orbits = np.zeros((len(used), width + 2))
    orbits[:, width] = 1 / lean.PHASE_SD_S**2
    count = energy = 0
    for row in rows:
        design = _design(row, width)
        white = _weight(row, len(design)) * (row.arc.track.whiten @ design)
        block = white.T @ white
        gram += block[:width, :width]
        rhs += block[:width, width + 1]
        orbit = orbits[indexes[row.orbit]]
        orbit[:width] += block[:width, width]
        orbit[width:] += block[width, width:]
        count += len(design)
        energy += block[-1, -1]
    return Statistics(gram, rhs, orbits, bound, used, count, float(energy))


def compile_library(path, cc="cc"):
    subprocess.run(
        [cc, *BUILD_FLAGS, "-fPIC", "-shared", str(SOURCE), "-lm", "-o", str(path)],
        check=True,
    )


class Kernel:
    def __init__(self, path):
        self.library = ctypes.CDLL(str(Path(path).resolve()))
        self.solve = self.library.leo_embedded_bvls
        arrays = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
        self.solve.argtypes = (
            [ctypes.c_size_t] * 2
            + [arrays] * 6
            + [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_size_t)]
        )
        self.solve.restype = ctypes.c_int

    def __call__(self, stats):
        width, orbits = len(stats.rhs), len(stats.orbit_ids)
        if (stats.gram.shape, stats.orbits.shape, stats.bounds.shape) != (
            (width, width),
            (orbits, width + 2),
            (width + orbits,),
        ):
            raise ValueError("inconsistent receiver and orbit blocks")
        coefficients = np.empty(width + orbits)
        covariance = np.empty((2, 2))
        kkt, steps = ctypes.c_double(), ctypes.c_size_t()
        result = self.solve(
            width,
            orbits,
            stats.gram,
            stats.rhs,
            stats.orbits,
            stats.bounds,
            coefficients,
            covariance,
            ctypes.byref(kkt),
            ctypes.byref(steps),
        )
        if result:
            raise ArithmeticError(f"bounded Schur solve did not certify convergence ({result})")
        return Solution(coefficients, covariance, kkt.value, steps.value)


def state(stats, coefficients, n_orbits):
    width = len(stats.rhs)
    phase = np.zeros(n_orbits)
    phase[list(stats.orbit_ids)] = coefficients[width:]
    return lean.State(
        coefficients[:2],
        1000 * coefficients[2:6],
        1000 * coefficients[6:10],
        phase,
        float(1000 * coefficients[10]) if width == 11 else 0.0,
    )


def coefficients(exact, stats):
    shared = np.r_[exact.xy, exact.bias / 1000, exact.drift / 1000]
    if len(stats.rhs) == 11:
        shared = np.r_[shared, exact.c_hz_per_ghz / 1000]
    return np.r_[shared, exact.phase[list(stats.orbit_ids)]]


def fit(rows, stats, solution, n_orbits):
    """Reconstruct the legacy Fit with stable per-track residual norms."""
    width = len(stats.rhs)
    params = solution.coefficients
    phase = dict(zip(stats.orbit_ids, params[width:], strict=True))
    prior = state(stats, params, n_orbits)
    prior_scaled = np.r_[
        prior.xy / 1000,
        prior.bias / (lean.PERIOD / np.sqrt(12)),
        prior.drift / 1500,
        prior.c_hz_per_ghz / 200000,
        params[width:] / lean.PHASE_SD_S,
    ]
    raw_square, score = 0.0, float(prior_scaled @ prior_scaled)
    for row in rows:
        basis = _design(row, width)
        residual = basis[:, -1] - basis[:, :width] @ params[:width]
        residual -= basis[:, width] * phase[row.orbit]
        white = _weight(row, len(basis)) * (row.arc.track.whiten @ residual)
        raw_square += float(residual @ residual)
        score += float(white @ white)
    radius = np.sqrt(5.991 * np.linalg.eigvalsh(solution.position_covariance)[-1])
    return lean.Fit(prior, float(np.sqrt(raw_square / stats.row_count)), score, float(radius))
