from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def audit(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("dense_assignment_reuse")


def test_same_named_blocks_can_share_pre_weight_contractions_only(audit):
    gain, phase = ("hardware", 0), ("phase", 42)
    raw, noise = np.array([2., 3.]), np.array([40., 40.])
    a = dict(rows=2, candidate=42, alias=0, raw=raw, sigma=noise, normalized_response=raw/noise,
             final_weight=.5, normalized_design={gain: raw, phase: raw})
    same = dict(blocks={"track": a}, fixed_priors={gain: 1., phase: 1.}, coefficients={gain: 1., phase: 2.})
    reweighted = dict(same, blocks={"track": dict(a, final_weight=.7)}, coefficients={gain: 3., phase: 2.})
    report = audit.overlap(same, reweighted)
    assert report["same_group_statistics_rows"] == 2
    assert report["same_final_weight"] == report["same_block_and_final_weight"] == 0
    assert report["priors_exact"] == 2 and report["radio_coefficients_exact"] == 0

    changed_names = dict(same, blocks={"track": dict(a, normalized_design={gain: raw, ("phase", 50): raw})})
    report = audit.overlap(same, changed_names)
    assert report["same_assignment_rows"] == 2 and report["same_group_statistics_rows"] == 0
    assert report["equal_named_active_design_columns"] == 1


def test_generous_ceiling_charges_salvage_only_once(audit):
    def clock(seconds):
        return {"cpu_s": seconds}

    control = dict(solve=clock(26), route_details=dict(cold_clocks=clock(5), salvage_clocks=clock(2),
                   predictive_clocks=clock(1), certified_salvage=dict(profile_calls=31, support_trials=50)))
    bounds = audit.ceilings(control)
    assert bounds["saving_required_cpu_s"] == 10
    assert bounds["remaining_with_free_cold_cpu_s"] == 21
    assert bounds["remaining_with_free_cold_salvage_and_predictive_cpu_s"] == 18
