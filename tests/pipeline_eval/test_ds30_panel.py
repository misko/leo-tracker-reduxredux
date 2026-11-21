import json

import pytest

from tools.pipeline_eval.qualification import ds30_panel as panel
from tools.pipeline_eval.qualification import ds30_score as score


def test_replay_geometry_is_distinct_from_dataset_membership(tmp_path):
    path = tmp_path / "segment.json"
    meta = {
        "receiver_ids": [0, 1],
        "sample_rate_hz": 10_000_000,
        "configuration": {"window_ms": 20},
    }
    path.write_text(json.dumps(meta))
    entry = {"path": str(path), "sha256": "sha256:" + panel._sha(path)}
    row = {
        "recording_state": "complete",
        "sample_rate_hz": 10_000_000,
        "session_id": "session",
        "tracking_inputs": [{"path": "timing"}],
        "raw_recording": {"segments": [entry], "integrity_errors": []},
    }
    assert panel.geometry(row)
    assert not panel.geometry(dict(row, recording_state="incomplete"))
    assert not panel.geometry(dict(row, tracking_inputs=[]))
    path.write_text(json.dumps(dict(meta, receiver_ids=[0])))
    with pytest.raises(ValueError, match="commitment"):
        panel.geometry(row)
    entry["sha256"] = "sha256:" + panel._sha(path)
    assert not panel.geometry(row)


def test_scoring_keeps_withheld_and_missing_references_in_correct_denominators():
    rows = []
    for method in panel.METHODS:
        for calibration in score.ARMS:
            for case, fixed, error in [("a", True, 0.7), ("b", False, None), ("c", True, None)]:
                rows.append(
                    dict(
                        case=case,
                        method=method,
                        calibration=calibration,
                        fix=fixed,
                        error_km=error,
                        conditional_rf_rms_hz=10 if fixed else None,
                        detector_cpu_s=12,
                        end_to_end_wall_s=15,
                        recorded_span_s=20,
                        solver_wall_s=2,
                    )
                )
    values = score.summary(rows, {"a": [0, 0], "b": [0, 0], "c": None})
    assert len(values) == 6
    assert all(
        (r["assigned"], r["fixes"], r["reference_eligible"], r["scored_fixes"], r["within_1km"])
        == (3, 2, 2, 1, 1)
        for r in values
    )
    assert len(score.paired_results(rows)) == 12
    assert all(r["fixes_within_recorded_span"] == 2 for r in values)


def test_factor_agreement_only_compares_frequency_for_matched_peaks():
    def probe(i, peak=None):
        factors = (
            []
            if peak is None
            else [
                dict(
                    passed_fractional_margin_gate=True,
                    fractional_margin=0.2,
                    candidate_rank=0,
                    integer_epoch_sample=peak[0],
                    fractional_epoch_offset_samples=0.0,
                    fractional_tracking_cfo_hz=peak[1],
                )
            ]
        )
        return dict(
            visit_index=i,
            receiver_id=0,
            valid_start_counter=i * 200000,
            actual_rf_hz=11000000000,
            candidates=factors,
        )

    original = [probe(0, (3, 100)), probe(1), probe(2, (4, 300)), probe(3, (8, 100))]
    fast = [probe(0, (3, 120)), probe(1, (2, 100)), probe(2), probe(3, (99, 100))]
    r = score.factor_agreement(original, fast)
    assert r["matched_winners"] == r["both_accepted_different_winners"] == 1
    assert r["original_only"] == r["alternative_only"] == 1
    assert r["matched_median_abs_cfo_delta_hz"] == 20
    with pytest.raises(ValueError, match="opportunities"):
        score.factor_agreement(original, fast[::-1])
