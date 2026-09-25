from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def module():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("i20_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_edge_detection_and_symmetric_lattice() -> None:
    m = module()

    class Driver:
        @staticmethod
        def local_coordinate(origin, east, north):
            return {"latitude_deg": origin["latitude_deg"] + north, "longitude_deg": east}

    points = m.lattice(Driver, {"latitude_deg": 1.0}, (2.0, -3.0), 0.5)
    assert len(points) == 9
    assert not m.on_edge(points[4], (2.0, -3.0), 0.5)
    assert m.on_edge(points[0], (2.0, -3.0), 0.5)


def test_group_combination_is_equal_session_with_frozen_weights() -> None:
    m = module()
    point = {
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
        "east_km_from_parent": 0.0,
        "north_km_from_parent": 0.0,
    }
    audits = [
        {
            **point,
            "group_id": "20260921_00",
            "nominal_session_score": {"equal_session_nominal_capped_loss": 0.2},
        },
        {
            **point,
            "group_id": "20260921_16",
            "nominal_session_score": {"equal_session_nominal_capped_loss": 0.1},
        },
    ]
    result = m.combine(audits, [point])[0]
    assert result["weighted_equal_session_nominal_capped_loss"] == pytest.approx(
        0.2742 * 0.2 + 0.7258 * 0.1
    )


def test_effective_boundary_uses_optimizer_tolerance() -> None:
    from qualify import effective_boundary_ok

    row = {
        "rate_bound_s_h": 0.5,
        "scalar_optimizer_xatol_s_h": 2e-7,
        "effective_boundary_margin_s_h": 1e-6,
        "effective_boundary_rate_count": 0,
        "rates_s_h": {"1": 0.4999989},
    }
    assert effective_boundary_ok(row)
    row["rates_s_h"] = {"1": 0.499999}
    assert not effective_boundary_ok(row)


def test_parent_can_be_a_complete_reference_free_contract_without_claiming_qualification(
    tmp_path,
) -> None:
    m = module()
    parent = tmp_path / "parent.json"
    plan = tmp_path / "plan.json"
    parent.write_text(
        '{"schema":"ds1-iteration15-information-weighted-basin/v1","complete":true,"qualified":false,"reference_used_for_fit":false}'
    )
    plan.write_text(
        '{"reference_used_for_inference":false,"group_weights":{"20260921_00":0.2742,"20260921_16":0.7258},"group_taus_s":{"20260921_00":-0.75,"20260921_16":-0.5}}'
    )
    result, _ = m.verify_inputs(parent, plan)
    assert result["qualified"] is False


def test_postseal_evaluator_distance_is_zero_at_reference() -> None:
    path = Path(__file__).with_name("evaluate_postseal.py")
    spec = importlib.util.spec_from_file_location("i20_evaluate_test", path)
    assert spec and spec.loader
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    assert evaluator.distance_km(*evaluator.REFERENCE) == 0.0
