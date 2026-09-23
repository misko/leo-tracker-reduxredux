# ruff: noqa: I001
"""Unit tests for the bounded fixed-candidate grid sensitivity tool."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "research"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "measure_grid_resolution_sensitivity", TOOLS / "measure_grid_resolution_sensitivity.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_uniform_phases_are_reproducible_and_special_points_are_labeled():
    first, labels = MODULE.offset_samples(32, 20260923)
    second, second_labels = MODULE.offset_samples(32, 20260923)

    assert np.array_equal(first, second)
    assert labels == second_labels
    assert first.shape == (41, 2)
    assert np.all((first[:32] >= -0.5) & (first[:32] <= 0.5))
    assert labels[:32] == ["uniform"] * 32
    assert labels[-4:] == [
        "southwest_corner",
        "northwest_corner",
        "southeast_corner",
        "northeast_corner",
    ]


def test_score_trials_chooses_tau_from_training_not_heldout_rows():
    measured = np.array([0.0, 0.0, 0.0, 0.0])
    # tau 0 fits training exactly and has a held residual.  tau 1 has the
    # reverse pattern, so selecting on held data would wrongly choose it.
    predictions = np.array([[[0.0, 0.0, 10.0, 10.0], [10.0, 10.0, 0.0, 0.0]]])
    held, train, tau = MODULE.score_trials(
        measured,
        predictions,
        np.array([True, True, False, False]),
        np.array([True]),
    )

    assert tau.tolist() == [0]
    assert train.tolist() == [0.0]
    assert held.tolist() == [10.0]


def test_score_trials_can_hold_the_recorded_tau_fixed():
    measured = np.array([0.0, 0.0, 0.0, 0.0])
    predictions = np.array([[[0.0, 0.0, 10.0, 10.0], [10.0, 10.0, 0.0, 0.0]]])
    held, train, tau = MODULE.score_trials(
        measured,
        predictions,
        np.array([True, True, False, False]),
        np.array([True]),
        fixed_tau_index=1,
    )

    assert tau.tolist() == [1]
    assert train.tolist() == [0.0]
    assert held.tolist() == [10.0]


def test_invisible_trials_are_excluded_from_survival_not_counted_as_good():
    held, _, _ = MODULE.score_trials(
        np.zeros(4),
        np.zeros((1, 1, 4)),
        np.array([True, True, False, False]),
        np.array([False]),
    )
    coverage = MODULE.coverage_summary(held[None], np.array([4]), 200.0)

    assert np.isinf(held[0])
    assert coverage["pooled_track_survival_fraction"] == 0.0
    assert coverage["unique_observation_coverage_min"] == 0
