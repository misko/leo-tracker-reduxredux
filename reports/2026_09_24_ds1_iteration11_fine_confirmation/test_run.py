from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def module():
    path = Path(__file__).parent / "run.py"
    spec = importlib.util.spec_from_file_location("i11test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def row(tau: float, objective: float, exact: float = 0.1):
    return {
        "tau_s": tau,
        "fit": {"converged": True, "selection_objective": objective},
        "exact_comparison": {
            "exact_full_observation_capped_loss": exact,
            "exact_sgp4_gate": {"passed": True},
        },
    }


def test_fine_levels_and_common_tau_grid_are_predeclared():
    m = module()
    assert m.LEVELS_KM == (0.048828125, 0.0244140625, 0.01220703125)
    assert m.TAUS == (-1.25, -1.0, -0.75, -0.5, -0.25)


def test_symmetric_lattice_has_center_and_opposite_offsets():
    m = module()
    origin = {"latitude_deg": 37.0, "longitude_deg": -122.0}
    rows = m.lattice(origin, 0.048828125, origin)
    assert len(rows) == 9
    assert sorted({round(row["east_km_from_iteration10"], 8) for row in rows}) == pytest.approx(
        [-0.048828125, 0.0, 0.048828125], abs=1e-7
    )
    assert sorted({round(row["north_km_from_iteration10"], 8) for row in rows}) == pytest.approx(
        [-0.048828125, 0.0, 0.048828125], abs=1e-7
    )


def test_equal_weight_combination_and_independent_taus():
    m = module()
    point = {
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
        "east_km_from_iteration10": 0.0,
        "north_km_from_iteration10": 0.0,
    }
    scans = [
        {**point, "group_id": m.GROUPS[0], "rows": [row(-0.75, 0.02), row(-0.5, 0.03)]},
        {**point, "group_id": m.GROUPS[1], "rows": [row(-0.75, 0.10), row(-0.5, 0.11)]},
    ]
    proposal = m.combine([point], scans)[0]
    assert proposal["balanced_proposal_objective"] == pytest.approx(0.06)
    assert proposal["group_weighting"] == {m.GROUPS[0]: 0.5, m.GROUPS[1]: 0.5}
    assert len(proposal["proposal_taus"][m.GROUPS[0]]) == m.TOP_TAUS_PER_GROUP


def test_exact_selection_uses_equal_weights_and_group_specific_tau():
    m = module()
    point = {
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
        "east_km_from_iteration10": 0.0,
        "north_km_from_iteration10": 0.0,
        "balanced_proposal_objective": 0.1,
    }
    audits = [
        {**point, "group_id": m.GROUPS[0], **row(-1.0, 0.1, 0.02)},
        {**point, "group_id": m.GROUPS[0], **row(-0.5, 0.2, 0.03)},
        {**point, "group_id": m.GROUPS[1], **row(-1.0, 0.2, 0.12)},
        {**point, "group_id": m.GROUPS[1], **row(-0.5, 0.1, 0.10)},
    ]
    selected = m.select(audits, [point])[0]
    assert selected["balanced_exact_capped_loss"] == pytest.approx(0.06)
    assert selected["best_exact_by_group"][m.GROUPS[0]]["tau_s"] == -1.0
    assert selected["best_exact_by_group"][m.GROUPS[1]]["tau_s"] == -0.5
