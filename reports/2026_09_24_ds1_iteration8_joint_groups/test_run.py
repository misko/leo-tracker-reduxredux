from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def module():
    path = Path(__file__).parent / "run.py"
    spec = importlib.util.spec_from_file_location("i8test", path)
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


def test_spatial_union_deduplicates_across_groups():
    m = module()
    fixture = {
        "results": [
            {
                "candidates": [
                    {"latitude_deg": 1.0, "longitude_deg": 2.0},
                    {"latitude_deg": 3.0, "longitude_deg": 4.0},
                ]
            },
            {
                "candidates": [
                    {"latitude_deg": 1.0, "longitude_deg": 2.0},
                    {"latitude_deg": 5.0, "longitude_deg": 6.0},
                ]
            },
        ]
    }
    # This unit fixture has three points; the production cardinality guard is
    # deliberately kept at the public entrypoint rather than this pure helper.
    points = {m.coordinate_key(r) for group in fixture["results"] for r in group["candidates"]}
    assert points == {(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)}


def test_balanced_proposal_is_equal_group_mean_not_observation_pool():
    m = module()
    point = {"latitude_deg": 1.0, "longitude_deg": 2.0}
    scans = [
        {**point, "group_id": m.GROUPS[0], "rows": [row(-1.0, 0.02), row(-0.5, 0.03)]},
        {**point, "group_id": m.GROUPS[1], "rows": [row(-1.0, 0.10), row(-0.5, 0.11)]},
    ]
    proposal = m.build_joint_proposals(scans, [point])[0]
    assert proposal["balanced_proposal_objective"] == pytest.approx(0.06)
    assert proposal["group_weighting"] == {m.GROUPS[0]: 0.5, m.GROUPS[1]: 0.5}


def test_exact_selection_keeps_separate_group_taus_and_equal_weights():
    m = module()
    point = {"latitude_deg": 1.0, "longitude_deg": 2.0, "balanced_proposal_objective": 0.1}
    audits = [
        {
            "latitude_deg": 1.0,
            "longitude_deg": 2.0,
            "group_id": m.GROUPS[0],
            **row(-1.0, 0.1, 0.02),
        },
        {
            "latitude_deg": 1.0,
            "longitude_deg": 2.0,
            "group_id": m.GROUPS[0],
            **row(-0.5, 0.2, 0.03),
        },
        {
            "latitude_deg": 1.0,
            "longitude_deg": 2.0,
            "group_id": m.GROUPS[1],
            **row(-1.0, 0.2, 0.12),
        },
        {
            "latitude_deg": 1.0,
            "longitude_deg": 2.0,
            "group_id": m.GROUPS[1],
            **row(-0.5, 0.1, 0.10),
        },
    ]
    selected = m.select_exact(audits, [point])[0]
    assert selected["balanced_exact_capped_loss"] == pytest.approx(0.06)
    assert selected["best_exact_by_group"][m.GROUPS[0]]["tau_s"] == -1.0
    assert selected["best_exact_by_group"][m.GROUPS[1]]["tau_s"] == -0.5
