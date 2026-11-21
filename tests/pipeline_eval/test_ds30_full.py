import hashlib
import json
from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import ds30_full_inputs as inputs
from tools.pipeline_eval.qualification import ds30_full_report
from tools.pipeline_eval.qualification import ds30_full_score as score


def sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def indexed_recording(tmp_path):
    segment = tmp_path / "a-recording/segment-00000000"
    segment.mkdir(parents=True)
    rows = []
    for i in range(2):
        lo = 100 + i * 200010
        receipt = dict(host_delivery_clock=dict(realtime_ns=123456 + i, monotonic_ns=230 + i))
        if i == 0:
            receipt["utc_clock_bracket"] = dict(
                sample_counter=lo,
                before=receipt["host_delivery_clock"],
                after=receipt["host_delivery_clock"],
            )
        acquisition = dict(
            global_visit=i,
            sample_start=lo,
            sample_end=lo + 200000,
            generation=4,
            retune_receipt=json.dumps(receipt),
            complete=True,
            validity_authority="provider_attested",
            validity_includes_guard=True,
            quality_flags=["retune"] if i else [],
            actual_if_center_hz=100,
        )
        rows.append(
            dict(
                sequence=i,
                acquisition=acquisition,
                iq_sha256=sha(str(i).encode()),
                target_id="f",
                sample_count=200000,
                receiver_count=2,
            )
        )
    payload = b"".join(json.dumps(r).encode() + b"\n" for r in rows)
    (segment / "index.jsonl").write_bytes(payload)
    doc = dict(
        receiver_ids=[0, 1],
        sample_rate_hz=10_000_000,
        radio={"serial": "radio-a"},
        window_count=2,
        configuration=dict(
            window_ms=20, targets=[dict(target_id="f", channel=1, edge="upper", lnb_lo_hz=1000)]
        ),
        chunks=[
            dict(
                index_relative_path="index.jsonl",
                index_bytes=len(payload),
                first_sequence=0,
                index_sha256=sha(payload),
                window_count=2,
            )
        ],
    )
    path = segment / "manifest.json"
    path.write_text(json.dumps(doc))
    return dict(
        recording_id="a-recording",
        session_id=None,
        source_inputs=[],
        tracking_inputs=[],
        window_count=2,
        raw_recording=dict(segments=[dict(path=str(path), sha256=sha(path.read_bytes()))]),
    ), segment


def test_missing_contract_reconstructs_both_receivers_and_excludes_only_the_bad_visit(tmp_path):
    member, segment = indexed_recording(tmp_path)
    doc = inputs.index_timing(member)
    assert [p["receiver_id"] for p in doc["source"]["probes"]] == [0, 1]
    assert [p["visit_index"] for p in doc["source"]["probes"]] == [0, 0]
    assert doc["provenance"]["excluded_windows"][0]["visit"] == 1
    assert doc["provenance"]["processed_windows"] == 1
    assert len(doc["delivery_clocks"]) == 2 and doc["clock_anchor"]["sample_counter"] == 100
    published = deepcopy(doc)
    published["source"]["probes"][0]["candidates"] = [{"some": "detector result"}]
    inputs.check_timing(doc, published)
    published["source"]["probes"][0]["actual_rf_hz"] += 1
    with pytest.raises(ValueError, match="opportunities"):
        inputs.check_timing(doc, published)
    (segment / "index.jsonl").write_bytes(b"changed")
    with pytest.raises(ValueError, match="index digest"):
        inputs.index_timing(member)


def test_existing_source_inventory_is_verified_without_claiming_a_native_detector_contract(
    tmp_path,
):
    member, folder = indexed_recording(tmp_path)
    original = inputs.index_timing(member)
    seg = member["raw_recording"]["segments"][0]
    entry = dict(
        scope="segment-00000000", path=str(folder), manifest_digest=seg["sha256"], windows=2
    )
    path = tmp_path / "source.json"
    path.write_text(
        json.dumps(
            dict(
                schema_version=1,
                kind="fast-scan-source",
                recording_name="a-recording",
                window_count=2,
                segments=[entry],
            )
        )
    )
    member.update(
        source_inputs=[dict(path=str(path), sha256=original["source"]["input_manifest_sha256"])],
        session_id=original["source"]["session_id"],
        raw_authority_digest=sha(b"dataset metadata"),
    )
    inputs.check_timing(original, inputs.index_timing(member))
    member["tracking_inputs"] = [{"path": "published"}]
    with pytest.raises(ValueError, match="identity"):
        inputs.index_timing(member)
    path.write_text("{}")
    with pytest.raises(ValueError, match="inventory digest"):
        inputs.index_timing(member)


def test_full_comparison_keeps_missing_fixes_and_excludes_unmeasured_runtime(tmp_path):
    rows = []
    for arm in score.ARMS:
        for method in score.METHODS:
            original = method == "algo07v5"
            for i, (base, fast) in enumerate([(1.25, 0.75), (None, 1.5), (0.25, None)]):
                error = base if original else fast
                rows.append(
                    dict(
                        case=str(i),
                        method=method,
                        calibration=arm,
                        previous=i == 0,
                        recording_state="incomplete" if i == 1 else "complete",
                        archived_original=i != 1,
                        reference_eligible=True,
                        fix=error is not None,
                        error_km=error,
                        cpu=0,
                        hardware_span_s=10,
                        acquisition_wall_s=None if original and i != 1 else 2,
                        end_to_end_wall_s=None if original and i != 1 else (16 if original else 8),
                        solver_wall_s=6 if original else 3,
                        detector_cpu_s=None,
                        frequency_rms_hz=None,
                        frequency_score=None,
                    )
                )
    pairs = score.paired(rows)
    summary, comparison = score.summarize(rows, pairs)
    one = next(r for r in summary if r["group"] == "all" and r["method"] == "compact_two_scan")
    assert (one["assigned"], one["fixes"], one["within_1km"], one["within_2km"]) == (3, 2, 1, 2)
    assert one["fixes_within_capture_span"] == 2
    shared = next(r for r in comparison if r["group"] == "all")
    assert (
        shared["common_scored"] == 1
        and shared["compact_only_fixes"] == shared["original_only_fixes"] == 1
    )
    assert shared["paired_median_delta_km"] == -0.5
    assert shared["actual_paired_end_to_end_n"] == 1
    assert shared["actual_paired_end_to_end_median_speedup"] == 2
    assert shared["actual_paired_solver_n"] == 3
    runtime = ds30_full_report.matched_runtime(rows, pairs)
    assert [r[1] for r in runtime] == [3, 1, 0, 1]
    assert runtime[1][2:] == ["0.27", "0.27", "0.13", "0.13", "2.00"]
    assert ds30_full_report.capture_deadlines(rows, pairs) == [
        ["Complete captures", 0, 0, 0],
        ["Interrupted captures", 1, 0, 1],
    ]
    ds30_full_report.report(rows, pairs, summary, comparison, [], tmp_path)
    output = (tmp_path / "RESULTS.md").read_text()
    assert "All recordings | Compact | 2/3" in output
    assert "Position solver · all | 3" in output


def test_calibration_pairs_residuals_and_position_independently():
    rows = [
        dict(
            case="a",
            method="algo07v5",
            calibration="c0",
            error_km=1,
            frequency_rms_hz=100,
            frequency_score=9,
        ),
        dict(
            case="a",
            method="algo07v5",
            calibration="fitted_c",
            error_km=2,
            frequency_rms_hz=80,
            frequency_score=10,
        ),
        dict(
            case="b",
            method="algo07v5",
            calibration="c0",
            error_km=None,
            frequency_rms_hz=120,
            frequency_score=None,
        ),
        dict(
            case="b",
            method="algo07v5",
            calibration="fitted_c",
            error_km=5,
            frequency_rms_hz=80,
            frequency_score=None,
        ),
    ]
    original, compact = ds30_full_report.calibration_changes(rows)
    assert original == ["Original", 1, "1.000", 2, "-30.00", 1, "1.00"]
    assert compact == ["Compact", 0, "—", 0, "—", 0, "—"]


def test_readiness_audits_both_complete_and_interrupted_recordings(tmp_path):
    roster = []
    for label, archived, state in (("A", True, "complete"), ("B", False, "incomplete")):
        item = dict(
            id=label,
            archived_original=archived,
            previous=archived,
            recording_state=state,
            windows=6,
        )
        roster.append(item)
        case = dict(id=label, recording={"window_count": 6}, valid_visits=4, session_id=label)
        binding = dict(
            case=case, roster_sha256="cohort", archived_original=archived, index_parity=archived
        )
        (tmp_path / (label + ".json")).write_text(json.dumps(binding))
    audit = inputs.audit_bindings(roster, "cohort", tmp_path)
    assert audit["recorded_visits"] == 12 and audit["antenna_opportunities"] == 16
    assert audit["rebuilt_inputs"] == {"complete": 0, "incomplete": 1}
    assert audit["reconstructed_timing_matched_published"] == ["A"]
    assert audit["excluded_visits"] == 4 and set(audit["bindings"]) == {"A", "B"}
    roster[1]["windows"] += 1
    with pytest.raises(ValueError, match="input audit"):
        inputs.audit_bindings(roster, "cohort", tmp_path)
