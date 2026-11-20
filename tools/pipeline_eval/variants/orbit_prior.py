"""Constrain the light fixed-owner fit with causal TLE disagreement."""

from dataclasses import dataclass
from unittest.mock import patch

import numpy as np
from sgp4.api import Satrec

from leo.sky.frames import julian_day_from_utc_ns

from . import robust_em as lean
from . import robust_orbit_fit as exact

NS = 1_000_000_000


@dataclass(frozen=True)
class Element:
    lines: tuple[str, str]
    epoch_ns: int
    collected_ns: int


def from_lines(lines, collected_ns):
    sat = Satrec.twoline2rv(*lines)
    epoch = round((sat.jdsatepoch - 2440587.5 + sat.jdsatepochF) * 86400 * NS)
    return Element(tuple(lines), epoch, collected_ns)


def age_width(current, previous, *, anchor_ns, cutoff_ns):
    """Use equal-time TEME disagreement as a proxy for phase uncertainty."""
    if current is not None and not current.epoch_ns <= current.collected_ns <= cutoff_ns:
        raise ValueError("current geometry has an unauthorized TLE epoch or collection time")
    if previous is not None and not (
        current is not None
        and previous.epoch_ns <= previous.collected_ns <= current.collected_ns <= cutoff_ns
        and previous.epoch_ns + NS <= current.epoch_ns <= anchor_ns
    ):
        raise ValueError("previous element lies outside the causal geometry history")
    if previous is None:
        return dict(width_s=lean.PHASE_SD_S, status="no_previous_element", propagations=0)
    jd, fraction = julian_day_from_utc_ns(np.asarray([anchor_ns], dtype=np.int64))
    old = Satrec.twoline2rv(*previous.lines)
    new = Satrec.twoline2rv(*current.lines)
    if old.satnum != new.satnum:
        raise ValueError("two different NORAD IDs cannot form an orbit prior")
    failed_old, old_position, _ = old.sgp4(float(jd[0]), float(fraction[0]))
    failed_new, new_position, new_velocity = new.sgp4(float(jd[0]), float(fraction[0]))
    v = np.asarray(new_velocity)
    if (
        failed_old
        or failed_new
        or not np.isfinite([old_position, new_position, v]).all()
        or float(v @ v) == 0.0
    ):
        return dict(width_s=lean.PHASE_SD_S, status="propagation_failed", propagations=2)
    gap_s = (current.epoch_ns - previous.epoch_ns) / NS
    age_s = (anchor_ns - current.epoch_ns) / NS
    alignment = float((np.asarray(old_position) - new_position) @ v / (v @ v))
    return dict(
        status="historical_pair",
        propagations=2,
        alignment_s=alignment,
        age_s=age_s,
        gap_s=gap_s,
        width_s=float(np.clip(np.hypot(1.0, alignment * age_s / gap_s), 1.0, 15.0)),
    )


def adapt_fit(original, solver, widths, rows, n_orbits, half, arm):
    """Replace only the existing phase precision rows in the stock BVLS call."""
    active = sorted({row.orbit for row in rows})
    count = len(active)
    values = widths[active]
    if count == 0 or np.all(values == lean.PHASE_SD_S):
        return original(rows, n_orbits, half, arm)

    def solve(matrix, right, **kwargs):
        block = matrix[-count:, -count:]
        if not np.array_equal(block, np.eye(count) / lean.PHASE_SD_S):
            raise ValueError("stock orbital phase precision block changed")
        diagonal = np.diag_indices(count)
        block[diagonal] = 1 / values
        return solver(matrix, right, **kwargs)

    with patch.object(lean, "lsq_linear", solve):
        return original(rows, n_orbits, half, arm)


def fixed_fit(operation, widths, *args):
    """Use the same widths in the linear prior and exact backtracking score."""
    widths = np.asarray(widths, dtype=float)
    if widths.ndim != 1 or not np.isfinite(widths).all() or np.any(widths <= 0):
        raise ValueError("expected a finite positive prior width per orbit")
    if np.all(widths == lean.PHASE_SD_S):
        return operation(*args)
    stock_fit, stock_solver, stock_loss = lean.fit, lean.lsq_linear, exact._loss

    def fit(rows, n_orbits, half, arm):
        if widths.shape != (n_orbits,):
            raise ValueError("prior width vector does not bind to the numerical sky")
        return adapt_fit(stock_fit, stock_solver, widths, rows, n_orbits, half, arm)

    def objective(rows, tile, region, state):
        score, rms = stock_loss(rows, tile, region, state)
        correction = (state.phase / widths) ** 2 - (state.phase / lean.PHASE_SD_S) ** 2
        return score + float(correction.sum()), rms

    with patch.object(lean, "fit", fit), patch.object(exact, "_loss", objective):
        return operation(*args)
