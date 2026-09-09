"""Synthetic numerical/PNG fixtures; none assert RF capture or sensitivity."""

import io
from functools import lru_cache

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.presentation.adaptive_hop_analysis import adaptive_trajectory_configuration
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    AdaptiveHopFractionalCandidateV1,
    AdaptiveHopProbeAnalysisV1,
    AdaptiveHopVisitAnalysisV1,
)
from leo.scanner.adaptive_hop_presentation import OVERVIEW_ARTIFACTS, RenderedAdaptiveOverview
from leo.scanner.adaptive_hop_products import (
    AdaptiveHopAnalysisBindingV1,
    AdaptiveHopMetricsManifestV1,
    AdaptiveHopVisitReferenceV1,
)
from tests.scanner.adaptive_hop_fixtures import receipt_fixture
from tests.storage.test_adaptive_hop_analysis import fixture


@lru_cache
def png_fixture():
    figure = Figure(figsize=(2, 1), dpi=100)
    FigureCanvasAgg(figure)
    figure.subplots().plot([0, 1], [0, 1])
    stream = io.BytesIO()
    figure.savefig(stream, format="png")
    return stream.getvalue()


def rendered_fixture():
    return RenderedAdaptiveOverview(
        artifacts={name: png_fixture() for name in OVERVIEW_ARTIFACTS},
        trajectory_configuration_sha256=adaptive_trajectory_configuration(0.025).digest,
        selected_observation_count=0,
        association_count=0,
        truncated_association_count=0,
    )


def overview_fixture(monkeypatch, **kwargs):
    binding, products = fixture(monkeypatch, **kwargs)
    digest = "sha256:" + "1" * 64
    refs = tuple(
        AdaptiveHopVisitReferenceV1(
            visit_index=p.visit_index,
            relative_path=f"visit-{p.visit_index:06d}.v1.json.zst",
            compressed_sha256=digest,
            uncompressed_sha256=digest,
            compressed_bytes=1,
            uncompressed_bytes=2,
            probe_count=len(p.probes),
            candidate_count=sum(r.candidate_count for r in p.probes),
            fractional_candidate_count=sum(len(r.candidates) for r in p.probes),
            passed_fractional_candidate_count=sum(
                c.passed_fractional_margin_gate for r in p.probes for c in r.candidates
            ),
        )
        for p in products
    )
    manifest = AdaptiveHopMetricsManifestV1(
        session_id=binding.session_id,
        input_manifest_sha256=binding.input_manifest_sha256,
        binding_sha256=binding.sha256,
        configuration=binding.configuration,
        complete_visit_count=len(products),
        visits=refs,
        finalized_utc_ns=1,
    )
    return binding, manifest, products


def full_overview_fixture(*, rate=2_500_000, mode="adaptive", candidate_count=16):
    """Full source-time metadata and analytic candidates; no IQ or detector execution."""
    receipt = receipt_fixture(rate=rate, mode=mode, complete=True)
    cfg = AdaptiveHopAnalysisConfigurationV1(
        sample_rate_hz=rate, maximum_acquisition_candidates=candidate_count
    )
    digest = "sha256:" + "1" * 64
    binding = AdaptiveHopAnalysisBindingV1(
        receipt=receipt, configuration=cfg, input_manifest_sha256=digest
    )
    refs = tuple(
        AdaptiveHopVisitReferenceV1(
            visit_index=i,
            relative_path=f"visit-{i:06d}.v1.json.zst",
            compressed_sha256=digest,
            uncompressed_sha256=digest,
            compressed_bytes=1,
            uncompressed_bytes=2,
            probe_count=22,
            candidate_count=22 * candidate_count,
            fractional_candidate_count=22 * candidate_count,
            passed_fractional_candidate_count=22 * candidate_count,
        )
        for i in range(receipt.complete_visit_count)
    )
    manifest = AdaptiveHopMetricsManifestV1(
        session_id=binding.session_id,
        input_manifest_sha256=digest,
        binding_sha256=binding.sha256,
        configuration=cfg,
        complete_visit_count=receipt.complete_visit_count,
        visits=refs,
        finalized_utc_ns=1,
    )

    def products():
        origin = receipt.terminal.first_counter
        for event in receipt.events:
            probes = []
            for p in range(cfg.scheduled_probe_count):
                anchor = event.valid_start_counter + p * cfg.probe_stride_samples + 125
                relative = anchor - origin
                time_s = (relative + 0.375) / rate
                for rx in cfg.receiver_ids:
                    candidates = []
                    for rank in range(candidate_count):
                        frequency = (
                            400_000
                            - 1000 * time_s
                            + 2 * time_s**2
                            - rx * 600_000
                            + event.target_index * 10_000
                            + rank * 4000
                        )
                        candidates.append(
                            AdaptiveHopFractionalCandidateV1(
                                candidate_rank=rank,
                                integer_epoch_sample=125,
                                integer_device_sample_counter=anchor,
                                integer_session_sample=relative,
                                fractional_epoch_offset_samples=0.375,
                                fractional_time_s=time_s,
                                acquired_cfo_hz=frequency - 10,
                                integer_residual_cfo_hz=0,
                                integer_tracking_cfo_hz=frequency - 10,
                                integer_exact_score=0.03,
                                integer_control_score=0.01,
                                integer_margin=0.02,
                                fractional_residual_cfo_hz=10,
                                fractional_tracking_cfo_hz=frequency,
                                fractional_exact_score=0.055,
                                fractional_control_score=0.01,
                                fractional_margin=0.045,
                                passed_fractional_margin_gate=True,
                            )
                        )
                    probes.append(
                        AdaptiveHopProbeAnalysisV1(
                            receiver_id=rx,
                            probe_index=p,
                            probe_start_ms=p * 10,
                            candidate_count=candidate_count,
                            candidates=tuple(candidates),
                            unavailable_candidates=(),
                            winning_candidate_rank=0,
                        )
                    )
            yield AdaptiveHopVisitAnalysisV1(
                session_id=binding.session_id,
                input_manifest_sha256=digest,
                configuration=cfg,
                policy_generation=receipt.plan.policy.generation,
                source_origin_counter=origin,
                visit_index=event.visit_index,
                target_index=event.target_index,
                target=event.target,
                invalid_start_counter=event.invalid_start_counter,
                valid_start_counter=event.valid_start_counter,
                valid_end_counter=event.valid_start_counter + cfg.dwell_samples,
                actual_if_center_hz=event.target.if_center_hz,
                probes=tuple(probes),
            )

    return binding, manifest, products
