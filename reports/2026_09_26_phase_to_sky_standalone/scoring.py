"""Wrapped-phase catalogue scoring for the incidence-geometry prototype."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

try:
    from geometry import C_M_PER_S, TAU, wrap_radians
except ModuleNotFoundError:  # Supports report-local loading without a package install.
    _spec = importlib.util.spec_from_file_location(
        "incidence_geometry_for_scoring", Path(__file__).with_name("geometry.py"))
    _geometry = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_geometry)
    C_M_PER_S, TAU, wrap_radians = (
        _geometry.C_M_PER_S, _geometry.TAU, _geometry.wrap_radians)


def _arrays(phase_rad, projection, rf_hz, train_mask):
    phase = np.asarray(phase_rad, float)
    projection = np.asarray(projection, float)
    rf = np.asarray(rf_hz, float)
    train = np.asarray(train_mask, bool)
    if not (phase.shape == projection.shape == rf.shape == train.shape):
        raise ValueError("phase, projection, RF, and split must have identical shapes")
    if phase.ndim != 1 or not train.any() or train.all():
        raise ValueError("a one-dimensional nonempty train/held split is required")
    if np.any(~np.isfinite(rf)) or np.any(rf <= 1e9):
        raise ValueError("physical RF above 1 GHz is required")
    return phase, projection, rf, train


def circular_loss(error_rad):
    """Bounded chord loss, zero for phase-equivalent predictions."""
    return float(np.mean(1.0 - np.cos(np.asarray(error_rad, float))))


def fit_single_candidate(phase_rad, projection, rf_hz, train_mask,
                         baseline_grid_m):
    """Fit baseline length and one constant instrumental phase on train only."""
    phase, projection, rf, train = _arrays(
        phase_rad, projection, rf_hz, train_mask)
    baselines = np.asarray(baseline_grid_m, float)
    if baselines.ndim != 1 or not len(baselines) or np.any(~np.isfinite(baselines)):
        raise ValueError("finite one-dimensional baseline grid required")
    best = None
    for baseline in baselines:
        geometric = TAU * baseline * rf * projection / C_M_PER_S
        beta = np.angle(np.mean(np.exp(1j * (phase[train] - geometric[train]))))
        error = wrap_radians(phase - geometric - beta)
        candidate = dict(baseline_length_m=float(baseline),
                         instrumental_phase_rad=float(beta),
                         train_loss=circular_loss(error[train]),
                         held_loss=circular_loss(error[~train]),
                         residual_phase_rad=error)
        if best is None or candidate["train_loss"] < best["train_loss"]:
            best = candidate
    return best


def fit_double_difference(observed_rad, geometry_cycles_per_m, train_mask,
                          baseline_grid_m, fit_constant_phase=False):
    """Fit a simultaneous-signal phase difference on whole held-out groups."""
    observed = np.asarray(observed_rad, float)
    cycles = np.asarray(geometry_cycles_per_m, float)
    train = np.asarray(train_mask, bool)
    if not (observed.shape == cycles.shape == train.shape) or observed.ndim != 1:
        raise ValueError("observations, geometry, and split must be matching vectors")
    if not train.any() or train.all():
        raise ValueError("nonempty train and held sets required")
    best = None
    for baseline in np.asarray(baseline_grid_m, float):
        prediction = TAU * baseline * cycles
        beta = (np.angle(np.mean(np.exp(1j * (observed[train] - prediction[train]))))
                if fit_constant_phase else 0.0)
        error = wrap_radians(observed - prediction - beta)
        candidate = dict(baseline_length_m=float(baseline),
                         fitted_constant_phase_rad=float(beta),
                         train_loss=circular_loss(error[train]),
                         held_loss=circular_loss(error[~train]),
                         residual_phase_rad=error)
        if best is None or candidate["train_loss"] < best["train_loss"]:
            best = candidate
    return best
