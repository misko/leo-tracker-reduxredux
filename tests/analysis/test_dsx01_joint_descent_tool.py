"""The association envelope must be reconsidered inside descent, without GPS."""

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from run_dsx01_joint_descent import (  # noqa: E402
    STARTS,
    descend,
    signature,
    validate_discovery,
)


class Quadratic:
    lower = np.array([-12.5, -12.5])
    upper = -lower

    def __init__(self, target, offset):
        self.target, self.offset = target, offset

    def residual(self, x):
        return np.r_[x - self.target, self.offset]


def test_satellite_mode_switches_after_step_and_envelope_never_increases():
    models = [Quadratic(np.array([3, 0]), 2), Quadratic(np.array([4, 0]), 0)]
    result = descend(models, [0, 0])
    assert result["trace"][0]["mode"] == 0
    assert result["final_mode"] == 1
    assert len(result["switches"]) == 1
    assert result["switches"][0]["step"] == 1
    np.testing.assert_allclose(result["parameters"], [4, 0], atol=1e-4)
    assert np.all(np.diff([r["score"] for r in result["trace"]]) <= 0)
    for row in result["trace"]:
        assert row["score"] == min(row["hypothesis_scores"])


def test_step_cap_is_reported_instead_of_claiming_convergence():
    result = descend([Quadratic(np.array([4, 0]), 0)], [0, 0], max_steps=1)
    assert result["stopped"] == "step_budget"
    assert result["steps"] == 1
    with pytest.raises(ValueError, match="outside"):
        descend([Quadratic(np.zeros(2), 0)], [13, 0])


def test_full_two_km_disk_grid_has_81_distinct_regional_starts():
    starts = np.array(STARTS)
    assert starts.shape == (81, 2)
    assert len(set(map(tuple, starts))) == 81
    assert np.all(np.linalg.norm(starts, axis=1) <= 10)
    assert np.all(starts % 2 == 0)
    assert np.array_equal(starts[0], [0, 0])


def test_signatures_ignore_row_order_and_nuisance_state_but_include_aliases():
    rows = [dict(component="A", candidate_index=0, candidate_norad=12),
            dict(component="B", candidate_index=1, candidate_norad=13)]
    left = dict(seed=dict(rows=rows, state={"beta": [999]}), aliases=[0, 1])
    right = dict(seed=dict(rows=rows[::-1], state={"beta": [0]}), aliases=[1, 0])
    assert signature(left) == signature(right)
    right["aliases"][0] = 2
    assert signature(left) != signature(right)


def test_discovery_rejects_gps_future_bank_and_warm_inputs():
    audit = dict(bank_sha256="bank", cutoff_utc_ns=10, origin_utc_ns=11, candidate_count=5)
    original = dict(status="complete", case="S01", input_audit=audit,
                    GPS_or_following_TLE_used=False, discovery_provenance=dict(
                        zero_initial_radio_phase_and_smooth=True,
                        saved_atlas_labels_calibration_or_site_read=False,
                        GPS_or_following_TLE_used=False, candidate_count=5))
    validate_discovery(original, "S01", audit)
    for key, value in (("zero_initial_radio_phase_and_smooth", False),
                       ("saved_atlas_labels_calibration_or_site_read", True),
                       ("GPS_or_following_TLE_used", True)):
        bad = copy.deepcopy(original)
        bad["discovery_provenance"][key] = value
        with pytest.raises(ValueError, match="cold, causal"):
            validate_discovery(bad, "S01", audit)
    with pytest.raises(ValueError, match="mismatch"):
        validate_discovery(original, "S01", dict(audit, bank_sha256="other"))


def test_report_rejects_ignored_better_association_and_wrong_trajectory(tmp_path, monkeypatch):
    import report_dsx01_joint_descent as reporter

    monkeypatch.setattr(reporter, "OUTPUT", tmp_path)
    monkeypatch.setattr(reporter, "STARTS", [(0, 0)])
    directory = tmp_path / "S01"
    directory.mkdir()
    path = directory / "start_00.json"
    arm = dict(parameters=[0, 0], trace=[dict(
        point=[0, 0], score=1.0, hypothesis_scores=[1.0, 2.0])])
    record = dict(case="S01", start_id=0, status="complete", start_east_north_km=[0, 0],
                  GPS_or_following_TLE_used=False, hypotheses=[], discovery_bindings={},
                  input_audit={}, arms=dict(c0=copy.deepcopy(arm), fitted_c=copy.deepcopy(arm)))
    path.write_text(json.dumps(record))
    assert len(reporter.read_case("S01")[0]) == 1
    record["arms"]["c0"]["trace"][0]["score"] = 2.0
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="better available association"):
        reporter.read_case("S01")
    record["arms"]["c0"]["trace"][0]["score"] = 1.0
    record["arms"]["c0"]["parameters"] = [1, 0]
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="endpoint"):
        reporter.read_case("S01")
