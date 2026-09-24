from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE / "iteration5_timing_refinement.py"


def module():
    s = importlib.util.spec_from_file_location("i5test", SOURCE)
    assert s and s.loader
    m = importlib.util.module_from_spec(s)
    sys.modules[s.name] = m
    s.loader.exec_module(m)
    return m


def test_tau_grid_and_separation_shortlist():
    m = module()
    assert m.TAUS == (-2.25, -2.0, -1.75, -1.5, -1.25, -1.0, -0.75, -0.5, -0.25)
    scans = [
        {
            "group_id": "g",
            "rows": [
                {
                    "latitude_deg": 37 + n * 0.03,
                    "longitude_deg": -122.0,
                    "tau_s": t,
                    "fit": {"converged": True, "selection_objective": n + abs(t)},
                }
                for n in range(2)
                for t in m.TAUS
            ],
        }
    ]
    out = m.shortlist(scans, "g")
    assert len(out) >= len(m.TAUS)
    assert all(row["fit"]["converged"] for row in out)
