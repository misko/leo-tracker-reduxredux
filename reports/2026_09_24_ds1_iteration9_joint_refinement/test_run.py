from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def module():
    p = Path(__file__).parent / "run.py"
    s = importlib.util.spec_from_file_location("i9test", p)
    assert s and s.loader
    m = importlib.util.module_from_spec(s)
    sys.modules[s.name] = m
    s.loader.exec_module(m)
    return m


def test_symmetric_lattice_has_center_and_opposite_offsets():
    m = module()
    origin = {"latitude_deg": 37.0, "longitude_deg": -122.0}
    rows = m.lattice(origin, 0.78125, origin)
    assert len(rows) == 9
    assert {
        (round(r["east_km_from_iteration8"], 6), round(r["north_km_from_iteration8"], 6))
        for r in rows
    } == {(e, n) for e in (-0.78125, 0, 0.78125) for n in (-0.78125, 0, 0.78125)}


def test_equal_weight_combination_and_two_taus():
    m = module()
    p = {
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
        "east_km_from_iteration8": 0.0,
        "north_km_from_iteration8": 0.0,
    }

    def r(t, o):
        return {"tau_s": t, "fit": {"converged": True, "selection_objective": o}}

    scans = [
        {**p, "group_id": m.GROUPS[0], "rows": [r(-0.75, 0.02), r(-0.5, 0.03)]},
        {**p, "group_id": m.GROUPS[1], "rows": [r(-0.75, 0.10), r(-0.5, 0.11)]},
    ]
    out = m.combine([p], scans)[0]
    assert (
        out["balanced_proposal_objective"] == pytest.approx(0.06)
        and len(out["proposal_taus"][m.GROUPS[0]]) == 2
    )
