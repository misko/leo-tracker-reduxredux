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


def test_exact_rate_crossfit_uses_a_symmetric_causal_prior() -> None:
    class Search:
        REFERENCE_RF_HZ = 1.0
        LIGHT_KM_S = 1.0

        @staticmethod
        def receiver_ecef(_lat: float, _lon: float) -> tuple[np.ndarray, np.ndarray]:
            return np.zeros(3), np.asarray([0.0, 0.0, 1.0])

    class Engine:
        search = Search()

    count = 20
    row = {
        "session_id": "session",
        "track_id": "track",
        "times_s": list(np.arange(count, dtype=float)),
        "measured_hz": [0.0] * count,
        "candidates": [{"candidate_id": "42"}],
    }
    atlas = {
        RUN._atlas_key("session", "track", "42"): {
            "position": np.tile(
                np.asarray([[[1.0, 0.0, 0.0]]]), (len(RUN.RATE_GRID_S_H), count, 1)
            ),
            "velocity": np.zeros((len(RUN.RATE_GRID_S_H), count, 3)),
        }
    }
    posterior = RUN._rate_posteriors(Engine(), [row], atlas, 0.0, 0.0)
    assert set(posterior) == {("42", fold) for fold in range(RUN.FOLDS)}
    for weights in posterior.values():
        assert np.isclose(np.sum(weights), 1.0)
        assert np.isclose(weights @ np.asarray(RUN.RATE_GRID_S_H), 0.0)
    mse, means = RUN._candidate_fold_mse(Engine(), row, "42", atlas, 0.0, 0.0, posterior)
    assert np.allclose(mse, 0.0)
    assert np.allclose(means, 0.0)
