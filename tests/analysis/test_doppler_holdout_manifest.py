from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from leo.analysis.research.doppler_dataset_policy import load_doppler_dataset_policy
from leo.analysis.research.doppler_holdout_manifest import (
    MANIFEST_SCHEMA,
    DopplerHoldoutDerivedManifestV1,
    FrameMaskDispositionV1,
    HoldoutCaptureDispositionV1,
    SourceSupportPoint,
    best_source_supported_window,
    frame_opportunity_starts,
    load_derived_holdout_manifest,
    load_holdout_protocol,
    maximum_contiguous_supported,
    validate_derived_holdout_manifest,
    validate_protocol_authority,
)
from leo.contracts.digests import canonical_digest

ROOT = Path(__file__).parents[2]
POLICY_PATH = ROOT / "config" / "analysis" / "doppler-experiment-dataset-policy-v1.json"
PROTOCOL_PATH = ROOT / "config" / "analysis" / "doppler-holdout-feasibility-protocol-v1.json"


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _closed_non_evaluable_manifest() -> DopplerHoldoutDerivedManifestV1:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    protocol = load_holdout_protocol(PROTOCOL_PATH.read_bytes())
    captures = tuple(
        HoldoutCaptureDispositionV1(
            session_id=capture.session_id,
            recording_manifest_sha256=capture.recording_manifest_sha256,
            analysis_run_id=capture.analysis_run_id,
            analysis_manifest_sha256=capture.analysis_manifest_sha256,
            recording_manifest_uri=f"bulk://recordings/{capture.session_id}",
            analysis_manifest_uri=f"bulk://analysis/{capture.analysis_run_id}/manifest.json",
            raw_integrity_attestation_id="attestation-not-inspected-in-unit-test",
            scopes=(),
            episode=None,
            status="non_evaluable",
            failure_stage="source_selection",
            reason="no_source_supported_episode",
        )
        for capture in (policy.capture(item) for item in protocol.expected_capture_ids)
    )
    values = {
        "schema": MANIFEST_SCHEMA,
        "phase": "feasibility_only",
        "protocol_repository_commit": "0" * 40,
        "dataset_policy_repository_commit": protocol.dataset_policy_repository_commit,
        "dataset_policy_sha256": protocol.dataset_policy_sha256,
        "protocol_configuration_sha256": _digest(PROTOCOL_PATH.read_bytes()),
        "selector_implementation_sha256": f"sha256:{'1' * 64}",
        "even_estimator_implementation_sha256": f"sha256:{'2' * 64}",
        "manifest_contract_implementation_sha256": f"sha256:{'3' * 64}",
        "inventory_sha256": policy.inventory_sha256,
        "experiment_role": "holdout_foundation",
        "future_odd_qin_outcomes_opened": False,
        "candidate_estimators_run": False,
        "upstream_source_and_epoch_conditioning": (protocol.upstream_source_and_epoch_conditioning),
        "guarded_full_frame_iq_loaded": True,
        "odd_qin_symbols_demodulated_or_scored": False,
        "capture_count": 15,
        "evaluable_capture_count": 0,
        "minimum_evaluable_capture_count": protocol.minimum_evaluable_capture_count,
        "launch_gate": "fail",
        "runtime_seconds": 0.0,
        "captures": [item.model_dump(mode="json") for item in captures],
    }
    return DopplerHoldoutDerivedManifestV1.model_validate(
        {**values, "manifest_digest": canonical_digest(values)}
    )


def test_committed_protocol_is_exactly_bound_and_response_blind() -> None:
    policy_payload = POLICY_PATH.read_bytes()
    policy = load_doppler_dataset_policy(POLICY_PATH)
    protocol = load_holdout_protocol(PROTOCOL_PATH.read_bytes())

    validate_protocol_authority(protocol, policy, policy_sha256=_digest(policy_payload))

    assert protocol.expected_capture_ids == policy.role("holdout_foundation").capture_ids
    assert len(protocol.expected_capture_ids) == 15
    assert protocol.minimum_evaluable_capture_count == 10
    assert protocol.future_odd_qin_outcomes_opened_at_freeze is False
    assert protocol.candidate_estimators_permitted is False
    assert protocol.dynamic_discovery_permitted is False
    assert protocol.capture_substitution_permitted is False
    assert protocol.even_qin_mask.raw_span_loading == (
        "guarded-full-frame-loaded-before-even-only-demodulation"
    )
    assert "all-qin" in protocol.upstream_source_and_epoch_conditioning


def test_closed_derived_manifest_accounts_for_every_frozen_capture() -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    protocol = load_holdout_protocol(PROTOCOL_PATH.read_bytes())
    manifest = _closed_non_evaluable_manifest()

    validate_derived_holdout_manifest(manifest, protocol, policy)

    assert tuple(item.session_id for item in manifest.captures) == (protocol.expected_capture_ids)
    assert manifest.future_odd_qin_outcomes_opened is False
    assert manifest.odd_qin_symbols_demodulated_or_scored is False


def test_derived_manifest_rejects_capture_order_drift() -> None:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    protocol = load_holdout_protocol(PROTOCOL_PATH.read_bytes())
    manifest = _closed_non_evaluable_manifest()
    values = manifest.model_dump(mode="json", exclude={"manifest_digest"})
    values["captures"] = list(reversed(values["captures"]))
    reordered = DopplerHoldoutDerivedManifestV1.model_validate(
        {**values, "manifest_digest": canonical_digest(values)}
    )

    with pytest.raises(ValueError, match="capture order or membership"):
        validate_derived_holdout_manifest(reordered, protocol, policy)


def test_protocol_and_manifest_loaders_reject_duplicate_json_keys() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_holdout_protocol(b'{"schema":"one","schema":"two"}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_derived_holdout_manifest(b'{"schema":"one","schema":"two"}')


def test_frame_mask_contract_cannot_serialize_an_odd_response() -> None:
    with pytest.raises(ValidationError, match="odd_absolute_cfo_hz"):
        FrameMaskDispositionV1.model_validate(
            {
                "frame_start_sample": 1,
                "reference_sample": 2.0,
                "continuity_segment_id": 0,
                "status": "unsupported",
                "rejection_reasons": ["test_rejection"],
                "even_absolute_cfo_hz": None,
                "even_frequency_uncertainty_hz": None,
                "even_exact_coherence": None,
                "even_control_coherence": None,
                "even_coherence_margin": None,
                "even_search_boundary": False,
                "odd_absolute_cfo_hz": 123.0,
            }
        )


def test_source_window_selection_is_frozen_and_source_only() -> None:
    selector = load_holdout_protocol(PROTOCOL_PATH.read_bytes()).source_episode_selector
    points = tuple(
        SourceSupportPoint(
            source_id=f"sha256:{index:064x}",
            observation_id=f"sha256:{index + 100:064x}",
            sample_start=index * 50,
            margin=float(index % 4),
        )
        for index in range(30)
    )

    selected = best_source_supported_window(
        points,
        sample_rate_hz=1_000,
        probe_samples=10,
        selector=selector,
    )

    assert selected == points
    assert len(selected) == 30


def test_frame_lattice_and_contiguous_support_accounting_are_deterministic() -> None:
    starts = frame_opportunity_starts(
        epoch_sample=10,
        sample_rate_hz=2_500_000,
        device_sample_start=0,
        device_sample_stop=15_000,
        frame_content_samples=3_322,
    )

    assert starts == (10, 3343, 6677, 10010)
    assert maximum_contiguous_supported((False, True, True, False, True, True, True)) == 3
