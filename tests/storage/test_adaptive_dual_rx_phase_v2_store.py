from __future__ import annotations

import math

import pytest

from leo.scanner.adaptive_dual_rx_phase_product_v2 import (
    AdaptiveDualRxDoubleDifferenceHypothesisV2,
    AdaptiveDualRxPhaseVisitV2,
)
from leo.storage.adaptive_dual_rx_phase_v2 import AdaptiveDualRxPhaseStoreV2
from leo.storage.errors import BundleCorruptionError
from tests.presentation.adaptive_overview_fixtures import rendered_fixture


def digest(letter: str) -> str:
    return "sha256:" + letter * 64


def visit(index: int, *, qualified: bool = True) -> AdaptiveDualRxPhaseVisitV2:
    hypotheses = (
        (
            AdaptiveDualRxDoubleDifferenceHypothesisV2(
                hypothesis_index=0,
                low_rx0_tracking_cfo_hz=-90_000.0,
                high_rx0_tracking_cfo_hz=-60_000.0,
                alias_aware_signal_separation_hz=30_000.0,
                receiver_offset_hz=-560_000.0,
                wrapped_high_minus_low_rad=0.4,
                standard_error_rad=0.08,
                common_session_time_s=2.0,
                low_center_session_time_s=1.9999,
                high_center_session_time_s=2.0001,
                asynchronous_center_separation_s=0.0002,
                asynchronous_correction_standard_error_rad=0.01,
                direct_common_frame_count=0,
                phase_resultant_floor=0.9,
                exact_to_control_power_ratio_floor=4.0,
            ),
        )
        if qualified
        else ()
    )
    return AdaptiveDualRxPhaseVisitV2(
        session_id="scan-hop-phase-v2",
        input_manifest_sha256=digest("1"),
        glrt_binding_sha256=digest("2"),
        visit_index=index,
        target_index=index % 4,
        edge="lower",
        state="qualified" if qualified else "insufficient_signal",
        reason=(
            "phase_blind_two_signal_hypotheses"
            if qualified
            else "fewer_than_two_phase_blind_receiver_pairs"
        ),
        consistent_receiver_pair_count=2 if qualified else 1,
        phase_quality_pair_count=2 if qualified else 1,
        hypotheses=hypotheses,
    )


def test_resumable_checkpoints_and_immutable_finalization(tmp_path) -> None:
    store = AdaptiveDualRxPhaseStoreV2(tmp_path)
    store.write_visit(visit(0))
    store.write_visit(visit(0))
    store.write_visit(visit(1, qualified=False))
    assert store.completed_visits("scan-hop-phase-v2", digest("1"), digest("2")) == (0, 1)
    assert store.read_visit("scan-hop-phase-v2", digest("1"), digest("2"), 0) == visit(0)
    png = rendered_fixture().artifacts["coverage"]
    manifest = store.finalize(
        session_id="scan-hop-phase-v2",
        input_manifest_sha256=digest("1"),
        glrt_binding_sha256=digest("2"),
        glrt_metrics_manifest_sha256=digest("3"),
        total_visit_count=2,
        geometry_phase_state="unavailable",
        geometry_phase_reason="calibrated baseline and chain phase are unavailable",
        png=png,
    )
    assert manifest.state == "ready" and manifest.hypothesis_count == 1
    assert manifest.artifact is not None
    assert store.artifact(manifest, expected_sha256=manifest.artifact.sha256) == png
    with pytest.raises(BundleCorruptionError, match="cannot be overwritten"):
        store.write_visit(visit(0, qualified=False))
    store.close()


def test_finalize_requires_complete_checkpoint_inventory(tmp_path) -> None:
    store = AdaptiveDualRxPhaseStoreV2(tmp_path)
    store.write_visit(visit(1))
    with pytest.raises(ValueError, match="cover every GLRT visit"):
        store.finalize(
            session_id="scan-hop-phase-v2",
            input_manifest_sha256=digest("1"),
            glrt_binding_sha256=digest("2"),
            glrt_metrics_manifest_sha256=digest("3"),
            total_visit_count=2,
            geometry_phase_state="unavailable",
            geometry_phase_reason="missing calibration",
            png=rendered_fixture().artifacts["coverage"],
        )
    store.close()


def test_contract_rejects_inconsistent_async_time() -> None:
    with pytest.raises(ValueError, match="asynchronous time"):
        AdaptiveDualRxDoubleDifferenceHypothesisV2(
            hypothesis_index=0,
            low_rx0_tracking_cfo_hz=1.0,
            high_rx0_tracking_cfo_hz=10_002.0,
            alias_aware_signal_separation_hz=10_001.0,
            receiver_offset_hz=3.0,
            wrapped_high_minus_low_rad=math.pi,
            standard_error_rad=0.1,
            common_session_time_s=1.0,
            low_center_session_time_s=1.0,
            high_center_session_time_s=1.1,
            asynchronous_center_separation_s=0.2,
            asynchronous_correction_standard_error_rad=0.01,
            direct_common_frame_count=0,
            phase_resultant_floor=0.9,
            exact_to_control_power_ratio_floor=3.0,
        )
