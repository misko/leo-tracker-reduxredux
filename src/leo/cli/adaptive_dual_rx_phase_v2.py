"""Resume bounded saved-IQ dual-RX phase extraction and finalize V2 when complete."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from leo.application.adaptive_dual_rx_geometry_v2 import reconstruct_product_geometry
from leo.application.adaptive_dual_rx_phase_v2 import extract_phase_visit_v2
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.presentation.adaptive_dual_rx_phase_v2 import render_adaptive_dual_rx_phase_v2
from leo.scanner.adaptive_dual_rx_geometry_input_v1 import AdaptiveDualRxGeometryInputV1
from leo.scanner.adaptive_dual_rx_phase_product_v2 import AdaptiveDualRxGeometrySummaryV2
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_dual_rx_phase_v2 import AdaptiveDualRxPhaseStoreV2
from leo.storage.adaptive_hop import AdaptiveHopIqStore, GeometryBoundAdaptiveHopIqManifestV6
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore


def _bounded_visits(text: str) -> int:
    value = int(text)
    if not 1 <= value <= 20:
        raise argparse.ArgumentTypeError("maximum visits must lie in 1..20")
    return value


def run(
    bulk_root: Path,
    session_id: str,
    *,
    probe_stride_ms: int,
    maximum_visits: int,
    geometry_input: AdaptiveDualRxGeometryInputV1 | None = None,
) -> dict[str, object]:
    captures = AdaptiveHopIqStore(bulk_root, read_only=True)
    analyses = AdaptiveHopAnalysisStore(bulk_root, read_only=True)
    phases = AdaptiveDualRxPhaseStoreV2(bulk_root)
    try:
        inspected = captures.inspect(session_id)
        binding = bind_actual_visit_analysis(
            inspected.manifest.receipt,
            input_manifest_sha256=inspected.manifest_sha256,
            probe_stride_ms=probe_stride_ms,
        )
        if tuple(binding.configuration.receiver_ids) != (0, 1):
            raise ValueError("phase V2 requires simultaneous RX0 and RX1")
        completed = set(
            phases.completed_visits(session_id, binding.input_manifest_sha256, binding.sha256)
        )
        processed = 0
        with (
            AdaptiveHopAnalysisInputStore(captures).source(session_id) as source,
            analyses.job(binding) as job,
        ):
            metrics = job.manifest()
            if metrics is None:
                raise ValueError("phase V2 requires sealed GLRT metrics")
            indexes = job.completed_visits()
            for index in indexes:
                if index in completed:
                    continue
                analysis = job.read_visit(index)
                phase_visit = extract_phase_visit_v2(
                    source.read_visit(index),
                    analysis,
                    glrt_binding_sha256=binding.sha256,
                )
                phases.write_visit(phase_visit)
                completed.add(index)
                processed += 1
                if processed >= maximum_visits:
                    break
            complete = tuple(sorted(completed)) == indexes
            manifest = None
            if complete:
                visits = tuple(
                    phases.read_visit(
                        session_id, binding.input_manifest_sha256, binding.sha256, index
                    )
                    for index in indexes
                )
                qualified = any(visit.hypotheses for visit in visits)
                geometry_result = None
                geometry_summary = None
                if geometry_input is not None:
                    if not isinstance(inspected.manifest, GeometryBoundAdaptiveHopIqManifestV6):
                        raise ValueError("geometry phase requires capture-bound receiver geometry")
                    geometry_result = reconstruct_product_geometry(
                        inspected.manifest, visits, geometry_input
                    )
                    residuals = [
                        min(
                            point.ambiguity_candidates, key=lambda item: abs(item.residual_rad)
                        ).residual_rad
                        for point in geometry_result.points
                    ]
                    assert geometry_result.geometry_digest is not None
                    assert geometry_result.calibration_digest is not None
                    geometry_summary = AdaptiveDualRxGeometrySummaryV2(
                        input_digest=geometry_input.input_digest,
                        receiver_geometry_binding_digest=(
                            geometry_input.receiver_geometry_binding_digest
                        ),
                        geometry_digest=geometry_result.geometry_digest,
                        calibration_digest=geometry_result.calibration_digest,
                        direction_evidence_sha256=geometry_input.direction_evidence_sha256,
                        state=geometry_result.ambiguity_state,
                        reasons=geometry_result.reasons,
                        point_count=len(geometry_result.points),
                        ambiguity_candidate_count=sum(
                            len(point.ambiguity_candidates) for point in geometry_result.points
                        ),
                        residual_rms_rad=(
                            math.sqrt(sum(value * value for value in residuals) / len(residuals))
                            if residuals
                            else None
                        ),
                    )
                png = (
                    render_adaptive_dual_rx_phase_v2(visits, geometry_result) if qualified else None
                )
                geometry_state = (
                    "unavailable" if geometry_result is None else geometry_result.ambiguity_state
                )
                geometry_reason = (
                    "verified geometry/calibration/direction input was not supplied"
                    if geometry_result is None
                    else ";".join(geometry_result.reasons)
                )
                manifest = phases.finalize(
                    session_id=session_id,
                    input_manifest_sha256=binding.input_manifest_sha256,
                    glrt_binding_sha256=binding.sha256,
                    glrt_metrics_manifest_sha256=sha256_digest(
                        canonical_json_bytes(metrics.model_dump(mode="json"))
                    ),
                    total_visit_count=len(indexes),
                    geometry_phase_state=geometry_state,
                    geometry_phase_reason=geometry_reason,
                    png=png,
                    geometry=geometry_summary,
                )
        return {
            "state": "complete" if complete else "partial",
            "session_id": session_id,
            "processed_visits": processed,
            "checkpoint_visits": len(completed),
            "total_visits": len(indexes),
            "manifest": None if manifest is None else manifest.model_dump(mode="json"),
        }
    finally:
        phases.close()
        analyses.close()
        captures.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--probe-stride-ms", type=int, choices=(10, 120), default=120)
    parser.add_argument("--maximum-visits", type=_bounded_visits, default=20)
    parser.add_argument("--geometry-input", type=Path)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                run(
                    args.bulk_root,
                    args.session_id,
                    probe_stride_ms=args.probe_stride_ms,
                    maximum_visits=args.maximum_visits,
                    geometry_input=(
                        None
                        if args.geometry_input is None
                        else AdaptiveDualRxGeometryInputV1.model_validate_json(
                            args.geometry_input.read_bytes()
                        )
                    ),
                ),
                sort_keys=True,
            )
        )
    except Exception as error:
        print(
            json.dumps(
                {"state": "failed", "error_type": type(error).__name__, "message": str(error)[:512]}
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
