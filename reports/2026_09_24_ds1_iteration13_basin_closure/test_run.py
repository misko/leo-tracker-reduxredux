from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def module():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("iteration13_run_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def fit(loss: float) -> dict:
    return {
        "selection_objective": loss,
        "exact_full_observation_capped_loss": loss,
        "converged": True,
        "rate_boundary_count": 0,
    }


def test_lattice_is_symmetric_and_edge_rule_is_reference_free() -> None:
    m = module()

    class Driver:
        @staticmethod
        def local_coordinate(origin, east, north):
            return {"latitude_deg": origin["latitude_deg"] + north, "longitude_deg": east}

    rows = m.lattice(Driver, {"latitude_deg": 1.0}, (2.0, -3.0), 0.5)
    assert len(rows) == 9
    assert {row["east_km_from_iteration12"] for row in rows} == {1.5, 2.0, 2.5}
    assert {row["north_km_from_iteration12"] for row in rows} == {-3.5, -3.0, -2.5}
    assert m.is_edge(rows[0], (2.0, -3.0), 0.5)
    assert not m.is_edge(rows[4], (2.0, -3.0), 0.5)


def test_combine_uses_equal_group_weight_and_rejects_nonconvergence() -> None:
    m = module()
    point = {
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
        "east_km_from_iteration12": 0.0,
        "north_km_from_iteration12": 0.0,
    }
    audits = [
        {**point, "group_id": "20260921_00", "rate_only": fit(0.02)},
        {**point, "group_id": "20260921_16", "rate_only": fit(0.10)},
    ]
    rows = m.combine(audits, [point])
    assert rows[0]["balanced_selection_objective"] == pytest.approx(0.06)
    audits[0]["rate_only"]["converged"] = False
    with pytest.raises(ValueError, match="no converged coordinate"):
        m.combine(audits, [point])


def test_evaluator_distance_is_zero_at_reference() -> None:
    path = Path(__file__).with_name("evaluate_postseal.py")
    spec = importlib.util.spec_from_file_location("iteration13_evaluate_test", path)
    assert spec and spec.loader
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    assert evaluator.distance_km(evaluator.REFERENCE, evaluator.REFERENCE) == 0.0


def test_qualification_detects_objective_rank_divergence() -> None:
    path = Path(__file__).with_name("qualify.py")
    spec = importlib.util.spec_from_file_location("iteration13_qualify_test", path)
    assert spec and spec.loader
    qualifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qualifier)
    base = {
        "east_km_from_iteration12": 0.0,
        "north_km_from_iteration12": 0.0,
        "balanced_exact_capped_loss": 2.0,
    }
    raw = {
        "east_km_from_iteration12": 1.0,
        "north_km_from_iteration12": 0.0,
        "balanced_exact_capped_loss": 1.0,
    }
    result = qualifier.objective_agreement(
        [
            {
                "stage_index": 0,
                "translation_index": 0,
                "winner": base,
                "ranked_coordinates": [base, raw],
            }
        ]
    )
    assert result[0]["agrees"] is False
