from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def module():
    path = Path(__file__).parent / "iteration6_matched_exact_ablation.py"
    spec = importlib.util.spec_from_file_location("i6test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_top_three_per_tau_and_iteration4_retention():
    m = module()
    taus = (-1.0, -0.5)
    scans = [
        {
            "group_id": "g",
            "rows": [
                {
                    "latitude_deg": 37 + n * 0.01,
                    "longitude_deg": -122.0,
                    "tau_s": tau,
                    "fit": {"converged": True, "selection_objective": n},
                }
                for tau in taus
                for n in range(4)
            ],
        }
    ]
    i5 = {"tau_grid_s": taus, "spatial_scans": scans}
    i4 = {
        "reference_used_for_fit": False,
        "results": [
            {
                "group_id": "g",
                "winner": {"latitude_deg": 37.03, "longitude_deg": -122.0, "tau_s": -0.5},
            }
        ],
    }
    rows = m.shortlist(i5, i4, "g")
    assert len(rows) == 7
    assert sum(row["tau_s"] == -1.0 for row in rows) == 3
    assert any(row["selection_origin"] == "iteration4_exact_winner" for row in rows)


def test_exact_key_tie_breaks_by_tau_then_coordinate():
    m = module()
    a = {
        "exact_comparison": {"exact_full_observation_capped_loss": 0.1},
        "tau_s": -0.5,
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
    }
    b = {
        "exact_comparison": {"exact_full_observation_capped_loss": 0.1},
        "tau_s": -0.25,
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
    }
    assert m.exact_key(b) < m.exact_key(a)
