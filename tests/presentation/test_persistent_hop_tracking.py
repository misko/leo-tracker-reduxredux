from __future__ import annotations

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopCfoCandidate,
    reconstruct_persistent_hop_trajectories,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.states import StarlinkEdge
from leo.presentation.persistent_hop_tracking import render_persistent_hop_tracking_png


def test_tracking_renderer_plots_a_tle_blind_cross_channel_trajectory() -> None:
    epoch_ns = 1_788_400_000_000_000_000
    candidates = tuple(
        PersistentHopCfoCandidate(
            candidate_id=canonical_digest({"candidate": index}),
            source_group_id=canonical_digest({"source": index}),
            candidate_rank=0,
            session_id="scan-hop-render",
            input_manifest_digest=canonical_digest({"manifest": "render"}),
            raw_recording_authority_digest=canonical_digest({"raw": "render"}),
            radio_id="radio-render",
            stream_generation="generation-render",
            receiver_id=0,
            visit_index=index,
            probe_index=0,
            channel=1 if index < 10 else 2,
            edge=StarlinkEdge.LOWER,
            actual_rf_hz=10_709_687_500.0 if index < 10 else 10_959_687_500.0,
            source_sample_start=index * 50_000,
            source_sample_end=(index + 1) * 50_000,
            support_start_utc_ns=epoch_ns + index * 1_000_000_000,
            support_center_utc_ns=epoch_ns + index * 1_000_000_000 + 10_000_000,
            support_end_utc_ns=epoch_ns + index * 1_000_000_000 + 20_000_000,
            measured_cfo_hz=350_000.0 - 1_500.0 * index,
            standard_uncertainty_hz=400.0,
            factorial_support_moments_s=(1.0, 0.0, 1.0 / 60_000.0, 0.0),
            exact_score=0.15,
            control_score=0.10,
            margin=0.05,
        )
        for index in range(20)
    )
    trajectory = reconstruct_persistent_hop_trajectories(candidates)

    payload = render_persistent_hop_tracking_png(trajectory, candidates, ())

    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(payload) > 10_000
