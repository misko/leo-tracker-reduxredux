from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import one_lane_capture_results as results
from tools.pipeline_eval.qualification.one_lane_roster import audit_projection
from tools.pipeline_eval.variants import one_lane_schedule


def test_original_archive_without_detector_sha_preserves_full_clock_and_exclusions():
    doc = {
        "delivery_clocks": [31, 83, 104, 179, 195],
        "clock_anchor": {"counter": 18},
        "last_sample_counter": 200,
        "source": {"input_manifest_sha256": "a", "session_id": "case", "probes": []},
        "provenance": {
            "invalid_capture": 1,
            "excluded_windows": [{"visit": 2, "reason": "invalid"}],
            "window_count": 5,
            "processed_windows": 4,
        },
    }
    for visit, channel in [(0, 1), (1, 2), (3, 3), (4, 2)]:
        for rx in range(2):
            doc["source"]["probes"].append(
                dict(
                    visit_index=visit,
                    receiver_id=rx,
                    channel=channel,
                    edge="upper",
                    actual_rf_hz=100 + rx,
                    valid_start_counter=doc["delivery_clocks"][visit],
                    candidates=[{"passed_fractional_margin_gate": True}],
                )
            )
    # Channels 1 and 3 recorded the same physical center, despite different channel labels.
    rf = {(1, "upper"): 100, (2, "upper"): 200, (3, "upper"): 100}
    projected, ledger = one_lane_schedule.project(doc, rf)
    assert [(r["visit"], r["selected_receiver"]) for r in ledger] == [
        (0, 0),
        (1, 0),
        (3, 1),
        (4, 1),
    ]
    assert "detector_sha256" not in projected["provenance"]
    assert audit_projection(doc, projected, ledger)["positive_probes"] == 4
    altered = deepcopy(projected)
    altered["source"]["probes"][1]["actual_rf_hz"] += 1
    with pytest.raises(ValueError, match="retained lane changed or suppressed lane"):
        audit_projection(doc, altered, ledger)


def matched_controls():
    row = {
        "id": "DS26-test",
        "paired_capture_sha256": "original-native",
        "original_request_sha256": "original-request",
        "catalog_sha256": "original-catalogue",
        "tile": {"id": "original", "center": [1.0, 2.0]},
        "result": {
            "status": "withheld",
            "boundary": "fixture factors through paired position",
            "reason": "fixture has insufficient support",
            "metrics": {},
            "arms": {a: {"latlon": None} for a in results.ARMS},
        },
    }
    full = dict(row, native_sha256="fixed-four-native")
    one = dict(row, native_sha256="fixed-one-native", stock_native_sha256=full["native_sha256"])
    plan = {k: one[k] for k in one if k != "result"}
    measured = dict(row, native_sha256="capture-one-native", schedule_sha256="same-schedule")
    packet = {
        "clock_authority": "same-clock",
        "selected_visit_sha256": "same-schedule",
        "positive_probes": 3,
        "stock_positive_probes": 7,
    }
    audit = {
        "bindings": {"four": {"native_sha256": full["native_sha256"]}},
        "rf_authority": "same-clock",
        "probe_counts": {"selected": {"four": 3}, "discarded": {"four": 4}},
    }
    return full, one, plan, packet, measured, audit


def test_controls_allow_distinct_native_representation_only_with_exact_physical_mask():
    full, one, plan, packet, measured, audit = matched_controls()
    results.validate_controls(full, one, plan, packet, measured, audit)
    with pytest.raises(ValueError, match="same physical antenna mask"):
        results.validate_controls(
            full, one, plan, dict(packet, selected_visit_sha256="changed"), measured, audit
        )
    with pytest.raises(ValueError, match="different original measurements"):
        results.validate_controls(full, one, plan, packet, dict(measured, tile={}), audit)
    one["result"] = dict(one["result"], arms={"c0": {"latlon": None}})
    with pytest.raises(ValueError, match="calibration arms"):
        results.validate_controls(full, one, plan, packet, measured, audit)


def test_withheld_pair_preserves_rescue_and_rf_without_inventing_a_position(monkeypatch):
    ident = "DS26-test"
    monkeypatch.setattr(results, "CASES", (ident,))
    rows = []
    for arm in results.ARMS:
        for method, error, rf, status in (
            (results.CAPTURE_BOTH, 2.1, 40.0, "ok"),
            (results.CAPTURE_ONE, None, 10.0, "withheld"),
            (results.FOUR_BOTH, None, None, "timed_out"),
            (results.FOUR_ONE, 5.0, 20.0, "ok"),
        ):
            rows.append(
                dict(
                    id=ident,
                    method=method,
                    arm=arm,
                    published=error is not None,
                    error_km=error,
                    conditional_rf_rms_hz=rf,
                    status=status,
                    observations=3,
                    tracks=1,
                )
            )
    outcome = {(r["contrast"], r["arm"]): r for r in results.paired(rows)}
    lost = outcome["lane_capture", "c0"]
    assert lost["lost_fix"] and not lost["both_fix"] and not lost["within_10pct"]
    assert lost["delta_error_km"] is None and lost["delta_conditional_rf_rms_hz"] == -30.0
    rescue = outcome["lane_four", "fitted_c"]
    assert rescue["rescued_fix"] and rescue["control_status"] == "timed_out"
    with pytest.raises(ValueError, match="duplicate measured cell"):
        list(results.paired([*rows, rows[0]]))
