from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

import pytest

from leo.analysis.research.doppler_dataset_policy import (
    CaptureBinding,
    CaptureDisposition,
    authorize_capture,
    authorize_consumed_inputs,
    authorize_manifest_files,
    finalize_capture_dispositions,
    load_doppler_dataset_policy,
    verify_policy_inventory,
)

ROOT = Path(__file__).parents[2]
POLICY_PATH = ROOT / "config" / "analysis" / "doppler-experiment-dataset-policy-v1.json"
REPORT_PATH = ROOT / "reports" / "2026_08_25_doppler_experiment_dataset_policy.md"

HOLDOUT_IDS = (
    "cap-20260825T010019-89c2889553e0",
    "cap-20260825T015754-6bfe6b67b1be",
    "cap-20260825T020035-c9413370f93b",
    "cap-20260825T022235-0afd1298f096",
    "cap-20260825T030000-49e936766343",
    "cap-20260825T031245-4fbc260ab065",
    "cap-20260825T031521-ec8adc0e9426",
    "cap-20260825T033028-374381fbcd3a",
    "cap-20260825T033302-80fddf217eb5",
    "cap-20260825T034929-bc0480bdb4a8",
    "cap-20260825T035201-d0abaead734c",
    "cap-20260825T041207-a5f08ab5bd42",
    "cap-20260825T043656-2da9e806d487",
    "cap-20260825T050946-ab916a6d0eee",
    "cap-20260825T051221-0032700e2140",
)


def _policy_document() -> dict[str, object]:
    document = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _write_policy(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_committed_policy_freezes_the_reviewed_roles_and_holdout() -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)

    assert len(policy.captures) == 36
    assert policy.latest_permitted_session_id == "cap-20260825T150802-473cb5bbcbd6"
    assert policy.pre_inventory_capture_ids == (
        "cap-20260824T192019-9023840c8e9f",
        "cap-20260824T192252-9981b9c27853",
        "cap-20260824T192531-491832825b97",
        "cap-20260824T193733-1454b499b8bb",
        "cap-20260824T194009-34ae34f129bc",
        "cap-20260824T194245-1dfbc879df2b",
    )
    assert {role.name: len(role.capture_ids) for role in policy.roles} == {
        "holdout_foundation": 15,
        "rate_development": 16,
        "polynomial_injection": 3,
        "multi_radio": 4,
        "v3_v4_canary": 1,
    }
    holdout = policy.role("holdout_foundation")
    assert holdout.capture_ids == HOLDOUT_IDS
    assert holdout.minimum_evaluable_capture_count == 10
    assert {policy.capture(session_id).provenance_status for session_id in holdout.capture_ids} == {
        "post_fix_counter_authoritative_protocol_unopened"
    }
    other_ids = {
        session_id
        for role in policy.roles
        if role.name != "holdout_foundation"
        for session_id in role.capture_ids
    }
    assert not (set(holdout.capture_ids) & other_ids)


def test_inventory_hash_and_aug25_capture_bindings_are_exact() -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    inventory_path = verify_policy_inventory(policy, ROOT)
    digest = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    assert f"sha256:{digest}" == policy.inventory_sha256

    with inventory_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == policy.inventory_capture_count
    by_session = {row["capture_session_id"]: row for row in rows}
    for capture in policy.captures:
        if not capture.session_id.startswith("cap-20260825"):
            continue
        row = by_session[capture.session_id]
        assert row["capture_state"] == "committed"
        assert row["analysis_state"] == "succeeded"
        assert row["pipeline_lane"] == "standard"
        assert row["recording_manifest_digest"] == capture.recording_manifest_sha256
        assert row["analysis_run_id"] == capture.analysis_run_id
        assert row["analysis_manifest_digest"] == capture.analysis_manifest_sha256


def test_inventory_byte_drift_is_denied(tmp_path: Path) -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    inventory_path = tmp_path / policy.inventory_path
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_bytes((ROOT / policy.inventory_path).read_bytes() + b"\n")

    with pytest.raises(ValueError, match="inventory digest"):
        verify_policy_inventory(policy, tmp_path)


def test_exact_capture_binding_is_authorized() -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    expected = policy.capture(HOLDOUT_IDS[0])

    assert (
        authorize_capture(
            policy,
            experiment_role="holdout_foundation",
            session_id=expected.session_id,
            recording_manifest_sha256=expected.recording_manifest_sha256,
            analysis_run_id=expected.analysis_run_id,
            analysis_manifest_sha256=expected.analysis_manifest_sha256,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("role", "session_id"),
    [
        ("holdout_foundation", "cap-20260825T160000-aaaaaaaaaaaa"),
        ("rate_development", HOLDOUT_IDS[0]),
        ("unknown_role", HOLDOUT_IDS[0]),
    ],
)
def test_unlisted_new_or_wrong_role_capture_is_denied(role: str, session_id: str) -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    reference = policy.capture(HOLDOUT_IDS[0])

    with pytest.raises(ValueError):
        authorize_capture(
            policy,
            experiment_role=role,
            session_id=session_id,
            recording_manifest_sha256=reference.recording_manifest_sha256,
            analysis_run_id=reference.analysis_run_id,
            analysis_manifest_sha256=reference.analysis_manifest_sha256,
        )


@pytest.mark.parametrize(
    "field",
    [
        "recording_manifest_sha256",
        "analysis_run_id",
        "analysis_manifest_sha256",
    ],
)
def test_capture_binding_drift_is_denied(field: str) -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    reference = policy.capture(HOLDOUT_IDS[0])
    supplied = {
        "recording_manifest_sha256": reference.recording_manifest_sha256,
        "analysis_run_id": reference.analysis_run_id,
        "analysis_manifest_sha256": reference.analysis_manifest_sha256,
    }
    supplied[field] = (
        "capture-00000000000000000000000000000000"
        if field == "analysis_run_id"
        else f"sha256:{'0' * 64}"
    )

    with pytest.raises(ValueError, match="capture binding disagrees"):
        authorize_capture(
            policy,
            experiment_role="holdout_foundation",
            session_id=reference.session_id,
            **supplied,
        )


def test_consumed_input_ledger_rejects_duplicates() -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    capture = policy.capture(HOLDOUT_IDS[0])

    with pytest.raises(ValueError, match="duplicate consumed capture"):
        authorize_consumed_inputs(
            policy,
            experiment_role="holdout_foundation",
            inputs=(capture, capture),
        )


def test_holdout_ledger_requires_ten_evaluable_captures() -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    dispositions = tuple(
        CaptureDisposition(
            capture=policy.capture(session_id),
            status="evaluable" if index < 9 else "non_evaluable",
            reason="" if index < 9 else "predeclared source-support gate failed",
        )
        for index, session_id in enumerate(HOLDOUT_IDS)
    )

    with pytest.raises(ValueError, match="requires at least 10"):
        finalize_capture_dispositions(
            policy,
            experiment_role="holdout_foundation",
            dispositions=dispositions,
        )


def test_holdout_ledger_cannot_drop_failures() -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    dispositions = tuple(
        CaptureDisposition(capture=policy.capture(session_id), status="evaluable", reason="")
        for session_id in HOLDOUT_IDS[:10]
    )

    with pytest.raises(ValueError, match="complete capture ledger"):
        finalize_capture_dispositions(
            policy,
            experiment_role="holdout_foundation",
            dispositions=dispositions,
        )


def test_complete_holdout_ledger_with_ten_evaluable_captures_is_valid() -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    dispositions = tuple(
        CaptureDisposition(
            capture=policy.capture(session_id),
            status="evaluable" if index < 10 else "non_evaluable",
            reason="" if index < 10 else "predeclared source-support gate failed",
        )
        for index, session_id in enumerate(HOLDOUT_IDS)
    )

    assert (
        finalize_capture_dispositions(
            policy,
            experiment_role="holdout_foundation",
            dispositions=dispositions,
        )
        == dispositions
    )


def test_disposition_cannot_fabricate_capture_provenance() -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    reference = policy.capture(HOLDOUT_IDS[0])
    altered = CaptureBinding(
        session_id=reference.session_id,
        recording_manifest_sha256=reference.recording_manifest_sha256,
        analysis_run_id=reference.analysis_run_id,
        analysis_manifest_sha256=reference.analysis_manifest_sha256,
        provenance_status="post_fix_counter_authoritative_opened",
    )
    dispositions = (
        CaptureDisposition(capture=altered, status="evaluable", reason=""),
        *(
            CaptureDisposition(capture=policy.capture(session_id), status="evaluable", reason="")
            for session_id in HOLDOUT_IDS[1:]
        ),
    )

    with pytest.raises(ValueError, match="disposition binding disagrees"):
        finalize_capture_dispositions(
            policy,
            experiment_role="holdout_foundation",
            dispositions=dispositions,
        )


def test_manifest_file_bytes_must_match_policy(tmp_path: Path) -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    reference = policy.capture(HOLDOUT_IDS[0])
    recording_manifest = tmp_path / "recording-manifest.json"
    analysis_manifest = tmp_path / "analysis-manifest.json"
    recording_manifest.write_text("{}", encoding="utf-8")
    analysis_manifest.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="capture binding disagrees"):
        authorize_manifest_files(
            policy,
            experiment_role="holdout_foundation",
            session_id=reference.session_id,
            analysis_run_id=reference.analysis_run_id,
            recording_manifest_path=recording_manifest,
            analysis_manifest_path=analysis_manifest,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("dynamic_discovery", "dynamic_capture_discovery_forbidden"),
        ("holdout_overlap", "holdout-foundation captures"),
        ("opened_injection", "opened hard-null captures"),
        ("unopened_development", "restricted to previously opened captures"),
    ],
)
def test_policy_mutations_fail_closed(tmp_path: Path, mutation: str, message: str) -> None:
    document = _policy_document()
    authority = document["authority"]
    roles = document["roles"]
    captures = document["captures"]
    assert isinstance(authority, dict)
    assert isinstance(roles, dict)
    assert isinstance(captures, dict)

    if mutation == "dynamic_discovery":
        authority["dynamic_capture_discovery_forbidden"] = False
    elif mutation == "holdout_overlap":
        multi_radio = roles["multi_radio"]
        assert isinstance(multi_radio, dict)
        capture_ids = multi_radio["capture_ids"]
        assert isinstance(capture_ids, list)
        capture_ids.append(HOLDOUT_IDS[0])
        multi_radio["expected_capture_count"] = len(capture_ids)
    elif mutation == "opened_injection":
        injection = captures["cap-20260825T062228-886fe2dd9cde"]
        assert isinstance(injection, dict)
        injection["provenance_status"] = "post_fix_counter_authoritative_opened"
    elif mutation == "unopened_development":
        development = captures["cap-20260825T054455-47f684bbc3cc"]
        assert isinstance(development, dict)
        development["provenance_status"] = "post_fix_counter_authoritative_protocol_unopened"
    else:
        raise AssertionError(f"unknown mutation: {mutation}")

    with pytest.raises(ValueError, match=message):
        load_doppler_dataset_policy(_write_policy(tmp_path, document))


def test_duplicate_json_key_is_denied(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema":"first","schema":"second"}', encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_doppler_dataset_policy(path)


def test_policy_report_links_resolve_and_records_no_launch() -> None:
    report = REPORT_PATH.read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)]+)\)", report)
    assert links
    assert all((REPORT_PATH.parent / link).resolve().is_file() for link in links)
    assert "experiments not launched" in report
    assert "No raw IQ was opened" in report


def test_consumed_inputs_require_the_exact_policy_dataclass_values() -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    reference = policy.capture(HOLDOUT_IDS[0])
    altered = CaptureBinding(
        session_id=reference.session_id,
        recording_manifest_sha256=reference.recording_manifest_sha256,
        analysis_run_id=reference.analysis_run_id,
        analysis_manifest_sha256=f"sha256:{'f' * 64}",
        provenance_status=reference.provenance_status,
    )

    with pytest.raises(ValueError, match="capture binding disagrees"):
        authorize_consumed_inputs(
            policy,
            experiment_role="holdout_foundation",
            inputs=(altered,),
        )
