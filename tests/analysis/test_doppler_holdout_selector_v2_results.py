from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from leo.analysis.research.doppler_dataset_policy import load_doppler_dataset_policy
from leo.analysis.research.doppler_holdout_manifest import load_derived_holdout_manifest
from leo.analysis.research.doppler_holdout_selector_v2 import (
    load_derived_holdout_manifest_v2,
    load_holdout_protocol_v2,
    validate_derived_manifest_v2,
    validate_protocol_authority_v2,
)

ROOT = Path(__file__).parents[2]
POLICY = ROOT / "config/analysis/doppler-experiment-dataset-policy-v1.json"
PROTOCOL = ROOT / "config/analysis/doppler-holdout-feasibility-protocol-v2.json"
REPORT = ROOT / "reports/2026_08_26_doppler_holdout_selector_v2_results.md"
OUTPUT = ROOT / "reports/figures/2026_08_26_doppler_holdout_selector_v2"
MANIFEST = OUTPUT / "derived-manifest-v2.json"
RECEIPT = OUTPUT / "audit-receipt.json"


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def test_committed_v2_result_is_exact_closed_and_response_blind() -> None:
    policy = load_doppler_dataset_policy(POLICY)
    protocol = load_holdout_protocol_v2(PROTOCOL.read_bytes())
    frozen_payload = (ROOT / protocol.frozen_v1_input.path).read_bytes()
    frozen_v1 = load_derived_holdout_manifest(frozen_payload)
    manifest = load_derived_holdout_manifest_v2(MANIFEST.read_bytes())

    validate_protocol_authority_v2(
        protocol,
        policy,
        policy_sha256=_digest(POLICY.read_bytes()),
        frozen_v1_payload=frozen_payload,
        frozen_v1=frozen_v1,
    )
    validate_derived_manifest_v2(manifest, protocol, frozen_v1)

    assert manifest.protocol_repository_commit == ("d1aab4f65cc0bd69d9a25c025a0eca8967b49fe5")
    assert manifest.evaluable_capture_count == 10
    assert manifest.launch_gate == "pass"
    assert manifest.bulk_storage_accessed is False
    assert manifest.raw_iq_accessed is False
    assert manifest.future_odd_qin_outcomes_opened is False
    assert manifest.odd_qin_symbols_demodulated_or_scored is False
    assert manifest.candidate_estimators_run is False
    assert (
        sum(item.eligible_target_count for item in manifest.captures if item.status == "evaluable")
        == 5_413
    )


def test_exact_capture_dispositions_are_frozen() -> None:
    manifest = load_derived_holdout_manifest_v2(MANIFEST.read_bytes())
    expected = {
        "cap-20260825T010019-89c2889553e0": (0, "non_evaluable"),
        "cap-20260825T015754-6bfe6b67b1be": (18, "non_evaluable"),
        "cap-20260825T020035-c9413370f93b": (0, "non_evaluable"),
        "cap-20260825T022235-0afd1298f096": (911, "evaluable"),
        "cap-20260825T030000-49e936766343": (355, "evaluable"),
        "cap-20260825T031245-4fbc260ab065": (0, "non_evaluable"),
        "cap-20260825T031521-ec8adc0e9426": (920, "evaluable"),
        "cap-20260825T033028-374381fbcd3a": (918, "evaluable"),
        "cap-20260825T033302-80fddf217eb5": (442, "evaluable"),
        "cap-20260825T034929-bc0480bdb4a8": (112, "evaluable"),
        "cap-20260825T035201-d0abaead734c": (324, "evaluable"),
        "cap-20260825T041207-a5f08ab5bd42": (482, "evaluable"),
        "cap-20260825T043656-2da9e806d487": (457, "evaluable"),
        "cap-20260825T050946-ab916a6d0eee": (492, "evaluable"),
        "cap-20260825T051221-0032700e2140": (150, "non_evaluable"),
    }
    actual = {
        item.session_id: (item.eligible_target_count, item.status) for item in manifest.captures
    }
    assert actual == expected


def test_audit_receipt_hashes_every_generated_artifact() -> None:
    receipt = json.loads(RECEIPT.read_text())
    for artifact in receipt["artifacts"].values():
        path = OUTPUT / artifact["path"]
        assert path.stat().st_size == artifact["bytes"]
        assert _digest(path.read_bytes()) == artifact["sha256"]
    assert receipt["future_odd_qin_outcomes_opened"] is False
    assert receipt["odd_qin_symbols_demodulated_or_scored"] is False
    assert receipt["candidate_estimators_run"] is False


def test_report_links_resolve_and_pngs_are_static() -> None:
    text = REPORT.read_text()
    links = re.findall(r"\[[^]]+\]\(([^)]+)\)|!\[[^]]*\]\(([^)]+)\)", text)
    relative = [left or right for left, right in links]
    assert relative
    for link in relative:
        if "://" not in link:
            assert (REPORT.parent / link).is_file(), link
    for name in ("target-accounting.png", "target-rejections.png"):
        assert (OUTPUT / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
