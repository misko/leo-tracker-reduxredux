from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from leo.analysis.research.doppler_dataset_policy import load_doppler_dataset_policy
from leo.analysis.research.doppler_holdout_manifest import FrameMaskDispositionV1
from leo.analysis.research.doppler_holdout_selector_v2 import (
    TargetMaskDispositionV2,
    load_holdout_protocol_v2,
    select_target_mask_v2,
    sha256_bytes,
)

ROOT = Path(__file__).parents[2]
POLICY = ROOT / "config/analysis/doppler-experiment-dataset-policy-v1.json"
PROTOCOL = ROOT / "config/analysis/doppler-holdout-feasibility-protocol-v2.json"


def _row(index: int, *, supported: bool = True, segment: int = 4) -> FrameMaskDispositionV1:
    return FrameMaskDispositionV1(
        frame_start_sample=1 + index,
        reference_sample=1.0 + index,
        continuity_segment_id=segment if supported else None,
        status="supported" if supported else "unsupported",
        rejection_reasons=() if supported else ("synthetic_rejection",),
        even_absolute_cfo_hz=100.0 if supported else None,
        even_frequency_uncertainty_hz=10.0 if supported else None,
        even_exact_coherence=0.1 if supported else None,
        even_control_coherence=0.01 if supported else None,
        even_coherence_margin=0.09 if supported else None,
        even_search_boundary=False,
    )


def test_protocol_is_exact_15_response_blind_and_offline() -> None:
    protocol = load_holdout_protocol_v2(PROTOCOL.read_bytes())
    policy = load_doppler_dataset_policy(POLICY)

    assert protocol.expected_capture_ids == policy.role("holdout_foundation").capture_ids
    assert protocol.minimum_evaluable_capture_count == 10
    assert protocol.future_odd_qin_outcomes_opened_at_freeze is False
    assert protocol.candidate_estimators_permitted is False
    assert protocol.dynamic_discovery_permitted is False
    assert protocol.capture_substitution_permitted is False
    assert protocol.bulk_storage_access_permitted is False
    assert tuple(item.minimum_supported_frames for item in protocol.history_gates) == (
        8,
        50,
        200,
    )
    assert sha256_bytes(POLICY.read_bytes()) == protocol.dataset_policy_sha256


def test_target_selector_is_strict_past_and_uses_identical_history_gates() -> None:
    protocol = load_holdout_protocol_v2(PROTOCOL.read_bytes())
    rows = tuple(_row(index) for index in range(451))

    selected = select_target_mask_v2(rows, sample_rate_hz=750, protocol=protocol)

    assert selected[449].status == "eligible"
    assert tuple(item.supported_frame_count for item in selected[449].histories) == (
        15,
        93,
        375,
    )
    assert selected[199].status == "ineligible"
    assert "history_500ms_count" in selected[199].rejection_reasons


def test_selector_ignores_even_cfo_values_after_support_is_frozen() -> None:
    protocol = load_holdout_protocol_v2(PROTOCOL.read_bytes())
    original = tuple(_row(index) for index in range(451))
    changed = tuple(
        row.model_copy(update={"even_absolute_cfo_hz": 1_000_000.0 + index})
        for index, row in enumerate(original)
    )

    left = select_target_mask_v2(original, sample_rate_hz=750, protocol=protocol)
    right = select_target_mask_v2(changed, sample_rate_hz=750, protocol=protocol)

    assert left == right


def test_selector_rejects_history_from_another_continuity_segment() -> None:
    protocol = load_holdout_protocol_v2(PROTOCOL.read_bytes())
    rows = tuple(_row(index, segment=3 if index < 400 else 4) for index in range(451))

    selected = select_target_mask_v2(rows, sample_rate_hz=750, protocol=protocol)

    assert selected[-1].status == "ineligible"
    assert "history_500ms_count" in selected[-1].rejection_reasons


def test_target_contract_forbids_odd_response_fields() -> None:
    with pytest.raises(ValidationError, match="odd_absolute_cfo_hz"):
        TargetMaskDispositionV2.model_validate(
            {
                "frame_start_sample": 1,
                "reference_sample": 1.0,
                "continuity_segment_id": None,
                "target_even_qin_supported": False,
                "histories": [
                    {"horizon_ms": 20.0, "supported_frame_count": 0, "supported_span_ms": 0},
                    {"horizon_ms": 125.0, "supported_frame_count": 0, "supported_span_ms": 0},
                    {"horizon_ms": 500.0, "supported_frame_count": 0, "supported_span_ms": 0},
                ],
                "status": "ineligible",
                "rejection_reasons": ["synthetic_rejection"],
                "odd_absolute_cfo_hz": 7.0,
            }
        )


def test_protocol_loader_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_holdout_protocol_v2(b'{"schema":"one","schema":"two"}')
