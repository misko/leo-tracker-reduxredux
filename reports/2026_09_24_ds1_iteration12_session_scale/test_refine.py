from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def module():
    path = Path(__file__).with_name("refine.py")
    spec = importlib.util.spec_from_file_location("iteration12_refine_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def _fit(loss: float) -> dict:
    return {
        "selection_objective": loss,
        "exact_full_observation_capped_loss": loss,
        "converged": True,
        "scale_reaches_guard": False,
    }


def test_refinement_combines_groups_with_equal_weight_and_fixed_grid():
    m = module()
    audits = []
    for north in (-m.SPACING_KM, 0.0, m.SPACING_KM):
        for east in (-m.SPACING_KM, 0.0, m.SPACING_KM):
            for group, loss in [("20260921_00", 0.02), ("20260921_16", 0.10)]:
                audits.append(
                    {
                        "group_id": group,
                        "latitude_deg": 1.0,
                        "longitude_deg": 2.0,
                        "east_km_from_iteration12_level1": east,
                        "north_km_from_iteration12_level1": north,
                        "baseline_rate_only": _fit(loss),
                        "common_plus_session_scale": _fit(loss),
                    }
                )
    rows = m.combine(audits, "common_plus_session_scale")
    assert len(rows) == 9
    assert rows[0]["balanced_selection_objective"] == pytest.approx(0.06)
    assert rows[0]["all_converged"]
    assert rows[0]["all_scale_guards_clear"]
