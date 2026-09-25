from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def module():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("i24_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


class LinearOrbit:
    @staticmethod
    def quartic(nodes, phase):
        out = nodes[:, 0].copy()
        out[:, 0] += phase
        return out

    @staticmethod
    def doppler(receiver, position, velocity, search):
        return position[:, 0]


def support_data(counts=(12, 12, 12), held_value=1e9):
    tracks = []
    train = []
    for index, count in enumerate(counts):
        tracks.extend([f"s:t{index}"] * count)
        train.extend([True] * count)
    tracks.append("held:poison")
    train.append(False)
    n = len(tracks)
    return SimpleNamespace(
        y=np.asarray(list(np.arange(n - 1, dtype=float)) + [held_value]),
        train=np.asarray(train, dtype=bool),
        track=np.asarray(tracks, object),
        source=np.asarray(["68739"] * (n - 1) + ["held-only-source"], object),
        session=np.asarray(["s"] * n, object),
        age_h=np.linspace(-1.0, 1.0, n),
        p_nodes=np.zeros((n, 1, 3)),
        v_nodes=np.zeros((n, 1, 3)),
    )


def test_support_eligibility_requires_every_fold_to_leave_24_rows() -> None:
    m = module()
    assert m.support_record(support_data((12, 12, 12)), "68739")["eligible"]
    result = m.support_record(support_data((20, 4, 4)), "68739")
    assert not result["eligible"]
    assert "a_fold_leaves_fewer_than_24_training_rows" in result["ineligibility_reasons"]


def test_sparse_single_track_source_is_ineligible() -> None:
    m = module()
    result = m.support_record(support_data((4,)), "68739")
    assert not result["eligible"]
    assert result["training_tracks"] == 1
    assert result["training_observations"] == 4


def test_support_ignores_held_membership_and_values() -> None:
    m = module()
    first = m.support_record(support_data(held_value=1.0), "68739")
    second = m.support_record(support_data(held_value=1e12), "68739")
    assert first == second


def test_omitted_track_score_fits_only_one_cfo() -> None:
    m = module()
    data = support_data((4,))
    rows = np.flatnonzero(data.train)
    result = m.omitted_track_score(data, np.zeros(3), object(), LinearOrbit, rows, rate_s_h=0.0)
    assert result["fitted_cfo_hz"] == pytest.approx(1.5)
    assert result["observations"] == 4
    shifted = support_data((4,))
    shifted.y[rows] += 12345.0
    shifted_result = m.omitted_track_score(
        shifted, np.zeros(3), object(), LinearOrbit, rows, rate_s_h=0.0
    )
    assert shifted_result["robust_loss"] == pytest.approx(result["robust_loss"])


def test_profile_objective_is_built_from_explicit_rows_only() -> None:
    m = module()
    low = support_data(held_value=1.0)
    high = support_data(held_value=1e12)
    rows = np.flatnonzero(low.train)
    low_objective, low_many = m.make_objectives(low, np.zeros(3), object(), LinearOrbit, rows)
    high_objective, high_many = m.make_objectives(high, np.zeros(3), object(), LinearOrbit, rows)
    assert low_objective(0.25) == pytest.approx(high_objective(0.25))
    assert low_many(np.asarray([-0.2, 0.3])) == pytest.approx(high_many(np.asarray([-0.2, 0.3])))


def test_plan_seals_required_gate_and_zero_policy() -> None:
    m = module()
    plan = m.verified_json(Path(__file__).with_name("plan.json"))
    assert plan["rate_profile"]["diagnostic_bound_s_h"] == 1.0
    assert plan["gates"]["maximum_fold_rate_range_s_h"] == pytest.approx(0.1835323183)
    assert plan["eligibility"]["ineligible_prospective_rate_s_h"] == 0.0
    assert plan["mask_policy"].startswith("TRAIN rows alone")


def test_finalized_iteration23_source_is_sealed_and_code_bound() -> None:
    m = module()
    _i23, artifact, _plan = m.load_sources()
    assert artifact["complete"] is True
    assert artifact["bindings"]["runner"] == m.digest(m.I23_RUN)


def test_sign_basin_is_strict() -> None:
    m = module()
    assert m.sign_basin(-0.1) == "negative"
    assert m.sign_basin(0.0) == "zero"
    assert m.sign_basin(0.1) == "positive"


def test_sealed_artifact_enforces_required_source_outcomes() -> None:
    m = module()
    artifact = m.verified_json(Path(__file__).with_name("audit.json"))
    assert artifact["complete"] is True
    assert artifact["reference_used"] is False
    assert artifact["held_used_for_fit_score_gate_or_decision"] is False
    assert artifact["geographic_search_run"] is False
    assert len(artifact["explicit_audits"]["68739"]["folds"]) == 5
    assert {row["winning_sign_basin"] for row in artifact["explicit_audits"]["68739"]["folds"]} == {
        "positive"
    }
    for source in ("57248", "58683"):
        row = artifact["explicit_audits"][source]
        assert row["support"]["eligible"] is False
        assert row["prospective_rate_s_h"] == 0.0
        assert row["folds"] == []
