from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from leo.analysis.research.long_arc_dataset import (
    LongArcAccessRequestV1,
    PostFixLongArcCohortV1,
    authorize_long_arc_request,
    load_post_fix_long_arc_cohort,
    verify_external_manifest_binding,
    verify_repository_bindings,
)

ROOT = Path(__file__).parents[2]
REGISTRY_PATH = ROOT / "config" / "analysis" / "post-fix-long-arc-research-cohort-v1.json"
REPORT_PATH = ROOT / "reports" / "2026_08_26_post_fix_long_arc_research_cohort.md"
TIME_ADDENDUM_PATH = (
    ROOT / "reports" / "2026_08_26_wrong_time_specificity_and_orbital_time_shift.md"
)
LEDGER_PATH = ROOT / "docs" / "research" / "evidence-ledger.md"

ARC_9981 = "long-arc-9981-r19f2-s1-rx1-upper-0-30s"
ARC_150802 = "long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s"


def _document() -> dict[str, object]:
    value = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_registry(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _external_manifest_fixture(
    tmp_path: Path,
    cohort: PostFixLongArcCohortV1,
    arc_id: str,
    *,
    manifest_state: str = "committed",
) -> tuple[PostFixLongArcCohortV1, Path, Path]:
    arc = cohort.arc(arc_id)
    recording = tmp_path / f"{arc_id}-recording.json"
    analysis = tmp_path / f"{arc_id}-analysis.json"
    continuity = arc.continuity
    recording_document = {
        "session_id": arc.provenance.session_id,
        "state": manifest_state,
        "streams": [
            {
                "stream_id": arc.path.stream_id,
                "state": arc.provenance.recording_stream_state,
                "captured_sample_count": continuity.observed_sample_count,
                "gap_map_sha256": continuity.gap_map_sha256,
                "timeline_sha256": continuity.timeline_sha256,
                "radio": {
                    "radio_id": arc.path.radio_id,
                    "serial": arc.path.radio_serial,
                },
                "applied_settings": {
                    "sample_rate_hz": arc.path.sample_rate_hz,
                    "bandwidth_hz": arc.path.bandwidth_hz,
                    "center_frequency_hz": arc.path.applied_if_hz,
                    "receiver_ids": [arc.path.receiver_id],
                },
                "timing": {
                    "first_sample": {
                        "earliest_utc_ns": arc.span.first_sample_earliest_utc_ns,
                        "estimate_utc_ns": arc.span.first_sample_estimate_utc_ns,
                        "latest_utc_ns": arc.span.first_sample_latest_utc_ns,
                        "method": "device_counter_anchored",
                    }
                },
                "continuity": {
                    "sample_loss_observable": continuity.sample_loss_observable,
                    "observed_sample_count": continuity.observed_sample_count,
                    "device_span_sample_count": continuity.device_span_sample_count,
                    "segment_count": continuity.segment_count,
                    "missing_sample_count": continuity.missing_sample_count,
                    "overflow_count": continuity.overflow_count,
                    "gap_count": continuity.gap_count,
                    "clipped_sample_count": continuity.clipped_sample_count,
                    "refill_count": continuity.full_capture_refill_count,
                },
            }
        ],
    }
    recording.write_text(json.dumps(recording_document, sort_keys=True), encoding="utf-8")
    recording_digest = _sha256(recording)
    analysis_document = {
        "session_id": arc.provenance.session_id,
        "run_id": arc.provenance.analysis_run_id,
        "pipeline_lane": arc.provenance.pipeline_lane,
        "input_manifest_digest": recording_digest,
    }
    analysis.write_text(json.dumps(analysis_document, sort_keys=True), encoding="utf-8")
    rebound_provenance = arc.provenance.model_copy(
        update={
            "recording_manifest_sha256": recording_digest,
            "analysis_manifest_sha256": _sha256(analysis),
        }
    )
    rebound_arc = arc.model_copy(update={"provenance": rebound_provenance})
    rebound_arcs = tuple(rebound_arc if item.arc_id == arc_id else item for item in cohort.arcs)
    return cohort.model_copy(update={"arcs": rebound_arcs}), recording, analysis


def _request(arc: object) -> LongArcAccessRequestV1:
    return LongArcAccessRequestV1(
        arc_id=arc.arc_id,
        session_id=arc.provenance.session_id,
        radio_id=arc.path.radio_id,
        radio_serial=arc.path.radio_serial,
        stream_id=arc.path.stream_id,
        receiver_id=arc.path.receiver_id,
        edge=arc.path.edge,
        sample_start=arc.span.sample_start,
        sample_stop_exclusive=arc.span.sample_stop_exclusive,
        recording_manifest_sha256=arc.provenance.recording_manifest_sha256,
        analysis_run_id=arc.provenance.analysis_run_id,
        analysis_manifest_sha256=arc.provenance.analysis_manifest_sha256,
    )


def test_committed_registry_contains_only_the_two_reviewed_post_fix_arcs() -> None:
    cohort = load_post_fix_long_arc_cohort(REGISTRY_PATH)

    assert cohort.authority.arc_ids == (ARC_9981, ARC_150802)
    assert cohort.authority.expected_arc_count == 2
    assert all(item.provenance.post_fix_classification == "POST_FIX" for item in cohort.arcs)
    assert all(item.research_status.holdout_authority is False for item in cohort.arcs)
    assert all(item.research_status.secure_identity_authority is False for item in cohort.arcs)

    arc_9981 = cohort.arc(ARC_9981)
    assert arc_9981.provenance.session_id == "cap-20260824T192252-9981b9c27853"
    assert arc_9981.provenance.recording_manifest_state == "committed"
    assert arc_9981.provenance.recording_stream_state == "complete"
    assert (arc_9981.span.sample_start, arc_9981.span.sample_stop_exclusive) == (
        0,
        75_000_000,
    )
    assert arc_9981.continuity.full_capture_refill_count == 573
    assert arc_9981.continuity.arc_refill_handoff_count is None
    assert len(arc_9981.source_binding.branch_ids) == 5

    arc_150802 = cohort.arc(ARC_150802)
    assert arc_150802.provenance.session_id == "cap-20260825T150802-473cb5bbcbd6"
    assert (arc_150802.span.sample_start, arc_150802.span.sample_stop_exclusive) == (
        93_937_500,
        128_500_000,
    )
    assert arc_150802.continuity.full_capture_refill_count == 573
    assert arc_150802.continuity.arc_refill_handoff_count == 132
    assert arc_150802.source_binding.scope_sha256 == (
        "sha256:7f564aad7246e3f24930ae2851c7ddfd58cf0879a052cb5fc304b897e063c74f"
    )


def test_parent_policy_and_every_committed_evidence_artifact_verify() -> None:
    cohort = load_post_fix_long_arc_cohort(REGISTRY_PATH)

    verified = verify_repository_bindings(cohort, ROOT)

    assert len(verified) == 6
    assert all(path.is_file() for path in verified)


@pytest.mark.parametrize("arc_id", [ARC_9981, ARC_150802])
def test_only_the_exact_capture_path_span_and_manifest_tuple_is_authorized(arc_id: str) -> None:
    cohort = load_post_fix_long_arc_cohort(REGISTRY_PATH)
    arc = cohort.arc(arc_id)
    request = _request(arc)

    assert authorize_long_arc_request(cohort, request) == arc

    widened = request.model_copy(
        update={"sample_stop_exclusive": request.sample_stop_exclusive + 1}
    )
    with pytest.raises(ValueError, match="disagrees with registry"):
        authorize_long_arc_request(cohort, widened)


def test_unlisted_arc_is_denied_without_dynamic_fallback() -> None:
    cohort = load_post_fix_long_arc_cohort(REGISTRY_PATH)
    request = _request(cohort.arc(ARC_9981)).model_copy(update={"arc_id": "newer-long-arc"})

    with pytest.raises(ValueError, match="not present"):
        authorize_long_arc_request(cohort, request)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("pre_fix", "post_fix_classification"),
        ("counterless", "sample_loss_observable"),
        ("missing_samples", "missing_sample_count"),
        ("span_drift", "sample count"),
        ("extra_arc", "expected arc count"),
    ],
)
def test_registry_mutations_fail_closed(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    document = _document()
    arcs = document["arcs"]
    assert isinstance(arcs, list)
    first = arcs[0]
    assert isinstance(first, dict)

    if mutation == "pre_fix":
        provenance = first["provenance"]
        assert isinstance(provenance, dict)
        provenance["post_fix_classification"] = "PRE_FIX"
    elif mutation == "counterless":
        continuity = first["continuity"]
        assert isinstance(continuity, dict)
        continuity["sample_loss_observable"] = False
    elif mutation == "missing_samples":
        continuity = first["continuity"]
        assert isinstance(continuity, dict)
        continuity["missing_sample_count"] = 1
    elif mutation == "span_drift":
        span = first["span"]
        assert isinstance(span, dict)
        span["sample_count"] = int(span["sample_count"]) - 1
    elif mutation == "extra_arc":
        arcs.append(first.copy())
    else:
        raise AssertionError(f"unknown mutation: {mutation}")

    with pytest.raises(ValueError, match=message):
        load_post_fix_long_arc_cohort(_write_registry(tmp_path, document))


def test_parent_policy_and_evidence_digest_drift_are_denied() -> None:
    cohort = load_post_fix_long_arc_cohort(REGISTRY_PATH)
    changed_authority = cohort.authority.model_copy(
        update={"parent_dataset_policy_sha256": f"sha256:{'0' * 64}"}
    )
    changed_parent = cohort.model_copy(update={"authority": changed_authority})
    with pytest.raises(ValueError, match="parent dataset policy digest"):
        verify_repository_bindings(changed_parent, ROOT)

    arc = cohort.arcs[0]
    changed_artifact = arc.evidence[0].model_copy(update={"sha256": f"sha256:{'0' * 64}"})
    changed_arc = arc.model_copy(update={"evidence": (changed_artifact,)})
    changed_evidence = cohort.model_copy(update={"arcs": (changed_arc, cohort.arcs[1])})
    with pytest.raises(ValueError, match="evidence digest"):
        verify_repository_bindings(changed_evidence, ROOT)


def test_duplicate_json_key_is_denied(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema":"first","schema":"second"}', encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_post_fix_long_arc_cohort(path)


def test_external_manifest_verifier_fails_before_any_iq_access(tmp_path: Path) -> None:
    cohort = load_post_fix_long_arc_cohort(REGISTRY_PATH)
    recording = tmp_path / "recording.json"
    analysis = tmp_path / "analysis.json"
    recording.write_text("{}", encoding="utf-8")
    analysis.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="recording manifest digest"):
        verify_external_manifest_binding(
            cohort,
            arc_id=ARC_9981,
            recording_manifest_path=recording,
            analysis_manifest_path=analysis,
        )


@pytest.mark.parametrize("arc_id", [ARC_9981, ARC_150802])
def test_external_manifest_verifier_accepts_committed_metadata_only_fixture(
    tmp_path: Path,
    arc_id: str,
) -> None:
    cohort, recording, analysis = _external_manifest_fixture(
        tmp_path,
        load_post_fix_long_arc_cohort(REGISTRY_PATH),
        arc_id,
    )

    verified = verify_external_manifest_binding(
        cohort,
        arc_id=arc_id,
        recording_manifest_path=recording,
        analysis_manifest_path=analysis,
    )

    assert verified.arc_id == arc_id


def test_external_manifest_verifier_rejects_non_authoritative_root_state(
    tmp_path: Path,
) -> None:
    cohort, recording, analysis = _external_manifest_fixture(
        tmp_path,
        load_post_fix_long_arc_cohort(REGISTRY_PATH),
        ARC_9981,
        manifest_state="complete",
    )

    with pytest.raises(ValueError, match="session or state"):
        verify_external_manifest_binding(
            cohort,
            arc_id=ARC_9981,
            recording_manifest_path=recording,
            analysis_manifest_path=analysis,
        )


def test_reports_resolve_local_links_and_state_the_scientific_limits() -> None:
    for report_path in (REPORT_PATH, TIME_ADDENDUM_PATH):
        report = report_path.read_text(encoding="utf-8")
        links = re.findall(r"\]\(([^)]+)\)", report)
        assert links
        assert all(
            link.startswith(("https://", "http://"))
            or (report_path.parent / link).resolve().is_file()
            for link in links
        )

    cohort_report = REPORT_PATH.read_text(encoding="utf-8")
    assert "no new\nexperiment run" in cohort_report
    assert "573` value is the refill count for each complete 60-second recording" in cohort_report
    assert "132 refill handoffs inside this arc" in cohort_report
    assert "committed `RecordingManifestV2` manifests" in cohort_report
    assert "PRE-FIX data\nremain excluded" in cohort_report

    addendum = TIME_ADDENDUM_PATH.read_text(encoding="utf-8")
    assert "catalogue-specificity null" in addendum
    assert "primary final\nholdout association actually fixed `tau = 0`" in addendum
    assert "does not expose that correction as a fitted scalar `tau`" in addendum
    assert "0023d1e240d0f9bb8bb4b289eaf83c08714a6ce7d86007a976d24874223497fa" in addendum
    assert "10.1109/TAES.2024.3513286" in addendum
    assert "`0.94–1.74 s`" in addendum
    assert "selected top-ranked TLE **elements** were\n`14.2–41.5 h` old" in addendum
    assert "**near-time catalogue null**" in addendum
    assert "**far-time catalogue null**" in addendum


def test_evidence_ledger_inventory_includes_both_new_reports() -> None:
    ledger = LEDGER_PATH.read_text(encoding="utf-8")
    report_paths = tuple((ROOT / "reports").rglob("*.md"))
    top_level_paths = tuple((ROOT / "reports").glob("*.md"))

    assert len(report_paths) == 132
    assert len(top_level_paths) == 121
    assert "all 132 tracked Markdown assets" in ledger
    assert "121 top-level reports" in ledger
    assert "2026_08_26_post_fix_long_arc_research_cohort.md" in ledger
    assert "2026_08_26_wrong_time_specificity_and_orbital_time_shift.md" in ledger
