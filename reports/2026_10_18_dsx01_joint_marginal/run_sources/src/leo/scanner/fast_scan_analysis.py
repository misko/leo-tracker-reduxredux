"""Fast-scan scientific stage, consuming verified windows through a narrow port."""

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from types import SimpleNamespace
from typing import Protocol

import numpy as np

from leo.analysis.starlink.acquisition import ReceiverFrequencyCalibration
from leo.analysis.starlink.templates import edge_frequencies_hz
from leo.contracts.digests import canonical_digest
from leo.contracts.fast_scan import (
    FastScanPolicyV1,
    FastScanReceiverV1,
    FastScanScoreV1,
    FastScanSegmentResultV1,
    FastScanWindowResultV1,
)
from leo.pipeline import ProductSpec, StageOutcome, StageResult, StageSpec
from leo.scanner.fast_scan_detector import Glrt64SearchGeometry, analyze_glrt64_dwell


@dataclass(frozen=True)
class VerifiedFastWindow:
    sequence: int
    iq_sha256: str
    acquisition: dict
    target: dict
    samples: np.ndarray


class FastWindowSource(Protocol):
    manifest_digest: str
    receiver_ids: tuple[int, ...]

    def windows(self) -> Iterable[VerifiedFastWindow]: ...


class Predictor(Protocol):
    def score_ci16(self, iq: np.ndarray) -> list[dict]: ...


def production_glrt(window, receivers):
    target = window.target
    actual = window.acquisition["actual_if_center_hz"]
    center = target["rf_center_hz"] - target["lnb_lo_hz"] - actual
    offsets = edge_frequencies_hz(target["edge"])
    width = min(
        800000.0, center + float(offsets.min()) + 1250000, 1250000 - center - float(offsets.max())
    )
    if width <= 0:
        raise ValueError("pilot lies outside recorded sample bandwidth")
    geometry = Glrt64SearchGeometry(
        tuple(
            ReceiverFrequencyCalibration(
                str(rx),
                center,
                canonical_digest({"target": target, "actual_if": actual, "rx": rx}).removeprefix(
                    "sha256:"
                ),
            )
            for rx in receivers
        ),
        -width,
        width,
        tuple(range(2, 302, 14)),
    )
    configuration = SimpleNamespace(
        dwell_samples=50000,
        probe_samples=50000,
        probe_stride_ms=20,
        probe_stride_samples=50000,
        scheduled_probe_count=1,
        sample_rate_hz=2500000,
        receiver_ids=receivers,
        probe_ms=20,
        glrt64_margin_gate=0.025,
        maximum_acquisition_candidates=8,
    )
    samples = np.empty((50000, len(receivers)), np.complex64)
    samples.real = window.samples[:, :, 0]
    samples.imag = window.samples[:, :, 1]
    result = analyze_glrt64_dwell(
        samples, configuration, edge=target["edge"], search_geometry=geometry
    )
    return tuple(
        FastScanReceiverV1(
            receiver_id=p.receiver_id, candidates=tuple(asdict(c) for c in p.candidates)
        )
        for p in result.probes
    )


def analyze_window(window, receiver_ids, predictor, policy, detector=production_glrt):
    a = window.acquisition
    t = window.target
    fields = dict(
        visit=a["global_visit"],
        segment_sequence=window.sequence,
        iq_sha256=window.iq_sha256,
        sample_start=a.get("sample_start"),
        sample_end=a.get("sample_end"),
        sample_start_utc_ns=a.get("sample_start_utc_ns"),
        generation=a.get("generation"),
        channel=t["channel"],
        edge=t["edge"],
        actual_if_hz=a.get("actual_if_center_hz"),
        lnb_reference_hz=t["lnb_lo_hz"],
        rf_mapping_authority=t.get("rf_mapping_authority", "unknown"),
    )
    valid = (
        window.samples.shape == (50000, len(receiver_ids), 2)
        and a.get("complete") is True
        and a.get("validity_authority") == "provider_attested"
        and a.get("validity_includes_guard") is True
        and not a.get("quality_flags")
        and a.get("actual_if_center_hz") is not None
        and type(a.get("sample_start")) is int
        and type(a.get("generation")) is int
        and a.get("sample_end") == a["sample_start"] + 50000
    )
    if not valid:
        return FastScanWindowResultV1(
            **fields, status="invalid_capture", reason="invalid sample support or retune quality"
        )
    scores = tuple(
        FastScanScoreV1(receiver_id=rx, **s)
        for rx, s in zip(receiver_ids, predictor.score_ci16(window.samples), strict=True)
    )
    passes = any(s.margin >= policy.threshold for s in scores)
    if policy.mode == "gated" and not passes:
        return FastScanWindowResultV1(
            **fields,
            status="skipped_fast_score",
            reason="all receiver scores below cutoff",
            scores=scores,
        )
    receivers = detector(window, receiver_ids)
    return FastScanWindowResultV1(
        **fields,
        status="processed",
        reason="paired GLRT completed",
        scores=scores,
        receivers=receivers,
    )


class FastScanAnalyzer:
    spec = StageSpec(
        key="fast-scan",
        algorithm_version="fast-scan-fractional-v1",
        configuration_schema="fast-scan-policy-v1",
        output_products=(ProductSpec(kind="fast-scan.glrt"),),
        accepted_outcomes=(StageOutcome.COMPLETE, StageOutcome.PARTIAL_COVERAGE),
    )

    def __init__(self, predictor_factory, detector=production_glrt):
        self.predictor_factory = predictor_factory
        self.detector = detector

    def analyze(self, context, iq, products, outputs):
        policy = FastScanPolicyV1.model_validate(context.stage_config)
        predictors = {}
        results = []
        for window in iq.windows():
            edge = window.target["edge"]
            if edge not in predictors:
                predictors[edge] = self.predictor_factory(edge, len(iq.receiver_ids))
            results.append(
                analyze_window(window, iq.receiver_ids, predictors[edge], policy, self.detector)
            )
        product = FastScanSegmentResultV1(
            manifest_digest=iq.manifest_digest, policy=policy, windows=tuple(results)
        )
        invalid = sum(r.status == "invalid_capture" for r in results)
        published = outputs.publish_json(
            self.spec.output_products[0], product.model_dump(mode="json")
        )
        return StageResult(
            outcome=StageOutcome.PARTIAL_COVERAGE if invalid else StageOutcome.COMPLETE,
            products=(published,),
            summary={
                "windows": len(results),
                "invalid": invalid,
                "processed": sum(r.status == "processed" for r in results),
                "skipped_fast_score": sum(r.status == "skipped_fast_score" for r in results),
            },
        )
