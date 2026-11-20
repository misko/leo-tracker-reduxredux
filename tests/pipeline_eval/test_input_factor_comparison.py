from copy import deepcopy
from hashlib import sha256

import pytest

from tools.pipeline_eval.qualification.input_factor_bridge import checked_history
from tools.pipeline_eval.qualification.input_factor_comparison import (
    NATIVE_KEYS,
    factor_changes,
    score,
)


def document(margin):
    return {
        "schema_version": 2,
        "clock_anchor": {},
        "last_sample_counter": 21,
        "source": dict.fromkeys(NATIVE_KEYS, "same")
        | {
            "analysis_manifest_sha256": "fixture",
            "probes": [
                {
                    "visit_index": 1,
                    "receiver_id": 0,
                    "valid_start_counter": 1,
                    "candidates": [
                        {
                            "fractional_margin": margin,
                            "passed_fractional_margin_gate": margin >= 0.025,
                        }
                    ],
                }
            ],
        },
        "provenance": {
            "run_id": "fixture",
            "scope": "fixture",
            "window_count": 1,
            "processed_windows": 1,
            "invalid_capture": 0,
            "skipped_fast_score": 0,
            "excluded_windows": [],
        },
    }


def test_factors_keep_acquisition_and_compare_candidates():
    a, b = document(0.024), document(0.025)
    result = factor_changes(a, b)
    assert result["capture_era"]["gate_passing_rows"] == 0
    assert result["ordinary"]["gate_passing_rows"] == result["changed_candidate_probe_rows"] == 1
    moved = deepcopy(b)
    moved["source"]["probes"][0]["receiver_id"] = 1
    with pytest.raises(ValueError, match="sampling support"):
        factor_changes(a, moved)
    b["source"]["probes"][0]["candidates"][0]["passed_fractional_margin_gate"] = False
    with pytest.raises(ValueError, match="gate"):
        factor_changes(a, b)


def test_history_rejects_lookahead_and_changed_bytes(tmp_path):
    paths = [tmp_path / name for name in ("8-current.tle", "2-prior.tle")]
    evidence = {}
    for p in paths:
        p.write_text(p.name)
        evidence[p.name] = sha256(p.read_bytes()).hexdigest()
    job = {"tle_root": str(tmp_path)}
    assert [row["utc_ns"] for row in checked_history(job, evidence, 9)] == [2, 8]
    with pytest.raises(ValueError, match="noncausal"):
        checked_history(job, evidence, 8)
    paths[0].write_text("changed")
    with pytest.raises(ValueError, match="digest"):
        checked_history(job, evidence, 9)


def test_position_threshold_and_frequency_are_independent():
    def arms(lat, rms):
        return dict.fromkeys(("c0", "fitted_c"), dict(latlon=[lat, 0], rf_rms_hz=rms))

    rows = score("fixture", [arms(0.01, 80), arms(0.0105, 75), arms(0.013, 65)], [0, 0])
    for row in rows:
        assert row["capture_within_10pct_original"]
        assert not row["ordinary_within_10pct_capture"]
        assert not row["ordinary_within_10pct_original"]
        assert row["compact_conditional_rms_delta_hz"] == -10
        assert row["fixed_factor_delta_km"] + row["changed_factor_delta_km"] == pytest.approx(
            row["total_delta_km"]
        )
