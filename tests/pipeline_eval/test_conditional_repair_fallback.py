import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import conditional_repair_fallback as trial


def candidate():
    arms = {arm: dict(gates={"tracks": [dict(component="curved", compatible=True)]},
                      linear_gates=[dict(component="predictive", compatible=arm == "c0")],
                      final_phase_change_s=.005, endpoint_east_north_km=[1, 2],
                      phase_reference=[.1]) for arm in trial.ARMS}
    return dict(arms=arms, entries=[{}], scan=object(), node=object(), keep=np.array([True]),
                powers=object(), means=object(), model=object())


@pytest.mark.parametrize("change", ("healthy", "curved", "region", "phase", "empty"))
def test_trigger_requires_predictive_failure_alone(change):
    saved = candidate()
    fitted = saved["arms"]["fitted_c"]
    if change == "healthy":
        fitted["linear_gates"][0]["compatible"] = True
    elif change == "curved":
        fitted["gates"]["tracks"][0]["compatible"] = False
    elif change == "region":
        fitted["endpoint_east_north_km"] = [1, 13]
    elif change == "phase":
        fitted["final_phase_change_s"] = np.nan
    else:
        saved["entries"] = []
    measured = {"repair": {"reason": "repair_original_joint_pair_gate"}}
    expected = None, "repair_original_joint_pair_gate"
    assert trial.conditional_fallback(saved, SimpleNamespace(half_width_km=12.5), measured) == expected
    assert "conditional_repair_fallback" not in measured


@pytest.mark.parametrize("move", (.010, .030))
def test_refits_both_arms_without_predictive_data(monkeypatch, move):
    saved = candidate()
    seen = []

    def fit(scan, node, keep, arm, reference, powers, means, model, entries, point):
        seen.append(arm)
        assert scan is saved["scan"] and node is saved["node"] and keep is saved["keep"]
        assert powers is saved["powers"] and means is saved["means"] and model is saved["model"]
        assert not entries
        assert reference == [.1] and point == [1, 2]
        original = saved["arms"][arm]
        return dict(original, gates={"tracks": [dict(component="curved", compatible=True, points=1)]},
                    linear_gates=[], endpoint_latlon=[38., -121.], RMS_hz=110., negative_twice_elbo=400.,
                    active_points=1, predictive_points=0, history=[{"movement_km": move}])

    monkeypatch.setattr(trial, "arm_finish", fit)
    measured = {"repair": {"reason": "repair_original_joint_pair_gate"}}
    result, reason = trial.conditional_fallback(saved, SimpleNamespace(half_width_km=12.5), measured)
    assert seen == list(trial.ARMS) and saved["entries"] == [{}]
    if move <= .020:
        assert reason is None and result["entries"] == []
        assert all(not arm["linear_gates"] for arm in result["arms"].values())
    else:
        assert result is None and reason == "repair_original_joint_pair_gate"
        assert measured["conditional_repair_fallback"]["reason"] == "conditional_pair_gate"
