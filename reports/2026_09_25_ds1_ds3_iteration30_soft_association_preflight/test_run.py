from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("iteration30_preflight", HERE / "run.py")
assert SPEC is not None and SPEC.loader is not None
RUN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUN
SPEC.loader.exec_module(RUN)


def test_deterministic_folds_cover_all_five() -> None:
    first = RUN.deterministic_folds("session", "track", 100)
    second = RUN.deterministic_folds("session", "track", 100)
    assert np.array_equal(first, second)
    assert set(first) == set(range(5))


def test_mixture_loss_is_continuous_and_penalizes_ambiguity() -> None:
    good = RUN.mixture_loss(np.asarray([10.0]), 50.0)
    ambiguous = RUN.mixture_loss(np.asarray([10.0, 20.0]), 50.0)
    bad = RUN.mixture_loss(np.asarray([300.0]), 50.0)
    assert good < ambiguous < bad
    assert 0.0 <= good <= 1.0
    assert 0.0 <= bad <= 1.0


def test_huber_location_limits_single_outlier() -> None:
    robust = RUN.huber_location(np.asarray([0.1, 0.1, 0.11, 0.1, 1.0]))
    assert robust < np.mean([0.1, 0.1, 0.11, 0.1, 1.0])
    assert abs(robust - 0.1) < 0.02


def test_bootstrap_margin_reproducible() -> None:
    mse = np.asarray([[100.0, 121.0, 100.0, 121.0, 100.0], [400.0] * 5])
    first = RUN.bootstrap_margin(mse, 0, 1, "fixed")
    second = RUN.bootstrap_margin(mse, 0, 1, "fixed")
    assert first == second
    assert first["margin_q10_hz"] > 0
