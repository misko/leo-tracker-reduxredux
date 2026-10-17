"""Identifiability and association safeguards for ensemble calibration variants."""

import importlib
from itertools import product
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    return importlib.import_module("evaluate_dsx01_consensus_calibration")


def linear_cohort(alias_period, count=7, noise=35.0, centers=None):
    result = []
    rng = np.random.default_rng(191)
    for i in range(count):
        center = 20 + 40 * i if centers is None else centers[i]
        t = np.linspace(center - 12, center + 12, 41)
        slope = -1800 + 600 * i
        common = 30000 + slope * (t - center)
        for rx in (1, 2):
            lift = int(i % 2 == 0 and rx == 2)
            y = common + (rx - 1) * (-9000 + 2 * (t - 150)) - lift * alias_period
            y += rng.normal(0, noise, len(t))
            coeff = np.polynomial.legendre.legfit((t - center) / 12, y, 1)
            key = f"test-RX{rx}-{i}"
            result.append(
                {
                    "key": key,
                    "source_id": "test",
                    "receiver": rx,
                    "channel": 1,
                    "bank": "CH1-4",
                    "rf_hz": 11.5e9,
                    "times": t,
                    "values": y,
                    "start_s": float(t.min()),
                    "end_s": float(t.max()),
                    "observation_ids": [f"{key}-{j}" for j in range(len(t))],
                    "pieces": [
                        {
                            "degree": 1,
                            "reference_time_s": center,
                            "time_scale_s": 12,
                            "coefficients_hz": coeff,
                            "start_s": float(t.min()),
                            "end_s": float(t.max()),
                        }
                    ],
                }
            )
    return result


@pytest.mark.parametrize("method", ("ransac", "compatibility", "trimmed", "em"))
def test_diverse_linear_ensemble_recovers_shared_calibration_and_joins(experiment, method):
    tracks = linear_cohort(experiment.PERIOD)
    pool = experiment.candidate_pool(tracks)
    assert len(pool) == 7
    assert all(not p["active_curvature"] and p["points"] == 82 for p in pool)
    packed = experiment.pack(pool)
    starts = experiment.initial_hypotheses(pool, packed, budget=12)
    calibration = experiment.fit_method(tracks, pool, packed, starts, method)
    beta = np.asarray(calibration["beta"])
    offset = (beta[2] - beta[0] + experiment.PERIOD / 2) % experiment.PERIOD - experiment.PERIOD / 2
    assert calibration["ensemble_eligible"]
    assert not calibration["historical_calibration_used"]
    assert calibration["data_rank"] == 2
    assert offset == pytest.approx(-9000, abs=30)
    assert (beta[6] - beta[4]) / 150 == pytest.approx(2, abs=0.2)
    # Rank two is sufficient for this relative RX contrast; the other paths remain unknown.
    assert experiment.calibration_gate(tracks[0], tracks[1], calibration)[0]
    result = experiment.fuse(tracks, calibration)
    assert result["output_tracks"] == 7
    assert len(result["accepted_edges"]) == 7
    assert all(g["degree"] <= 1 for g in result["merged_groups"])
    assert any(g["degree"] == 1 for g in result["merged_groups"])
    assert result["associated_points"] == 14 * 41
    assert len(result["ownership"]) == len(tracks)


@pytest.mark.parametrize("method", ("ransac", "compatibility", "trimmed", "em"))
def test_one_linear_pair_cannot_promote_its_own_calibration(experiment, method):
    tracks = linear_cohort(experiment.PERIOD, count=1)
    pool = experiment.candidate_pool(tracks)
    packed = experiment.pack(pool)
    starts = experiment.initial_hypotheses(pool, packed, budget=2)
    calibration = experiment.fit_method(tracks, pool, packed, starts, method)
    assert not calibration["ensemble_eligible"]
    assert experiment.calibration_gate(tracks[0], tracks[1], calibration) == (
        False,
        "insufficient_ensemble",
    )
    assert experiment.fuse(tracks, calibration)["output_tracks"] == 2


def test_single_curve_copied_many_times_cannot_supply_independent_votes(experiment):
    tracks = linear_cohort(experiment.PERIOD, count=1)
    pool = experiment.candidate_pool(tracks)
    copies = [dict(pool[0], left_key=f"a{i}", right_key=f"b{i}") for i in range(12)]
    assert len(experiment.independent_selection(copies, np.zeros(12))) == 1


def test_alias_lifts_are_applied_in_native_hz_before_rf_scaling(experiment):
    tracks = linear_cohort(experiment.PERIOD, count=1, noise=0.0)
    tracks[1]["rf_hz"] *= 1.08
    tracks[1]["channel"], tracks[1]["bank"] = 7, "CH5-8"
    tracks[1]["values"] = 1.08 * tracks[0]["values"] + 45000 - experiment.PERIOD
    pool = experiment.candidate_pool(tracks)
    packed = experiment.pack(pool)
    beta = np.array([0.0, 0.0, 0.0, 45.0, 0.0, 0.0, 0.0, 0.0])
    chi2, branches = experiment.distances(pool, packed, beta)
    assert chi2[0] < 1e-12
    assert pool[0]["lifts"][branches[0]] == (0, 1)


def test_unobservable_path_is_not_mistaken_for_zero_uncertainty(experiment):
    tracks = linear_cohort(experiment.PERIOD)
    pool = experiment.candidate_pool(tracks)
    packed = experiment.pack(pool)
    starts = experiment.initial_hypotheses(pool, packed, budget=3)
    calibration = experiment.fit_method(tracks, pool, packed, starts, "ransac")
    high = {**tracks[1], "channel": 7, "bank": "CH5-8", "rf_hz": 12.2e9}
    allowed, reason = experiment.calibration_gate(tracks[0], high, calibration)
    assert not allowed and reason == "unobservable_calibration"


def test_time_separation_matters_even_with_many_linear_pairs(experiment):
    tracks = linear_cohort(experiment.PERIOD, centers=np.linspace(140, 160, 7))
    pool = experiment.candidate_pool(tracks)
    packed = experiment.pack(pool)
    starts = experiment.initial_hypotheses(pool, packed, budget=3)
    calibration = experiment.fit_method(tracks, pool, packed, starts, "ransac")
    assert len(calibration["selected_pairs"]) == 7
    assert not calibration["ensemble_eligible"]


def test_bounded_solver_matches_exhaustive_small_quadratic_oracle(experiment):
    rng = np.random.default_rng(23)
    design = rng.normal(size=(60, 8))
    h = design.T @ design
    target = np.r_[rng.normal(0, 2, 4), [-7.0, 8.0, 6.0, -9.0]]
    rhs = h @ target
    expected_cost = np.inf
    for state in product((0, -1, 1), repeat=4):
        fixed = np.array([j + 4 for j, value in enumerate(state) if value], dtype=int)
        free = np.array([j for j in range(8) if j not in fixed])
        x = np.zeros(8)
        x[fixed] = [state[j - 4] * 3 for j in fixed]
        x[free] = np.linalg.solve(
            h[np.ix_(free, free)], rhs[free] - h[np.ix_(free, fixed)] @ x[fixed]
        )
        if np.max(abs(x[4:])) <= 3 + 1e-8 and np.max(abs(x[:4])) < experiment.BOUND[0]:
            expected_cost = min(expected_cost, float(0.5 * x @ h @ x - rhs @ x))
    actual = experiment.solve_box(h, rhs)
    assert np.all(abs(actual) <= experiment.BOUND + 1e-8)
    assert 0.5 * actual @ h @ actual - rhs @ actual == pytest.approx(expected_cost, abs=1e-7)
