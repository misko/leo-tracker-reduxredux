"""Run resumable broadband/pilot phase analysis on a sealed adaptive scan."""

import argparse
import json
import time
from pathlib import Path

from leo.analysis.starlink.relative_phase import extract_relative_phase
from leo.application.adaptive_relative_phase import relative_phase_priority, relative_phase_probes
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.presentation.adaptive_relative_phase import render_relative_phase
from leo.scanner.adaptive_hop_analysis import analyze_adaptive_hop_visit
from leo.scanner.adaptive_relative_phase import (
    MAXIMUM_VISITS,
    RelativePhaseArtifactV1,
    RelativePhaseManifestV1,
    RelativePhaseVisitV1,
    relative_phase_binding,
)
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from leo.storage.adaptive_relative_phase import RelativePhaseStore


def run(root, session_id, *, probe_stride_ms=120, maximum_seconds=120):
    if not 0 < maximum_seconds <= 560:
        raise ValueError("Phase budget must be in (0,560] seconds")
    started = time.monotonic()
    captures = AdaptiveHopIqStore(root, read_only=True)
    analyses = AdaptiveHopAnalysisStore(root, read_only=True)
    try:
        capture = captures.inspect(session_id)
        binding = bind_actual_visit_analysis(
            capture.manifest.receipt,
            input_manifest_sha256=capture.manifest_sha256,
            probe_stride_ms=probe_stride_ms,
        )
        digest = relative_phase_binding(binding.input_manifest_sha256, binding.sha256)
        with RelativePhaseStore(root).job(session_id, digest, writable=True) as output:
            existing = output.manifest()
            if existing:
                for artifact in existing.artifacts:
                    output.artifact(artifact.name, artifact.sha256)
                return dict(state="complete", manifest=existing.model_dump(mode="json"))
            applicable = tuple(binding.configuration.receiver_ids) == (0, 1)
            with analyses.job(binding) as metrics:
                if metrics.manifest() is None:
                    raise ValueError("Relative phase requires sealed GLRT metrics")
                indexes = metrics.completed_visits()
                ranked = []
                if applicable:
                    for index in indexes:
                        priority = relative_phase_priority(metrics.read_visit(index))
                        if priority is not None:
                            ranked.append((-priority, index))
            selected = tuple(sorted(index for _, index in sorted(ranked)[:MAXIMUM_VISITS]))
            rows = []
            with AdaptiveHopAnalysisInputStore(captures).source(session_id) as source:
                ordinals = {v.event.visit_index: i for i, v in enumerate(source.visits)}
                for index in selected:
                    row = output.visit(index)
                    if row is None:
                        if time.monotonic() - started >= maximum_seconds:
                            return dict(
                                state="partial",
                                selected_visit_count=len(selected),
                                checkpoint_visits=len(rows),
                            )
                        config = binding.configuration.model_copy(update={"probe_stride_ms": 20})
                        ordinal = ordinals[index]
                        analysis = analyze_adaptive_hop_visit(source, ordinal, configuration=config)
                        probes = relative_phase_probes(analysis)
                        try:
                            evidence = extract_relative_phase(
                                source.read_visit(ordinal),
                                config.sample_rate_hz,
                                analysis.target.edge,
                                probes,
                            )
                            state = "supported" if evidence["supported"] else "insufficient_signal"
                            reason = (
                                "disjoint_band_check_passed"
                                if state == "supported"
                                else "disjoint_band_check_failed"
                            )
                        except ValueError as exc:
                            evidence = {}
                            state = "insufficient_signal"
                            reason = str(exc)[:512]
                        row = RelativePhaseVisitV1(
                            session_id=session_id,
                            binding_sha256=digest,
                            visit_index=index,
                            state=state,
                            reason=reason,
                            evidence=evidence,
                        )
                        output.write_visit(row)
                    rows.append(row)
            images = render_relative_phase(
                rows, session_id=session_id, total_visits=len(indexes), applicable=applicable
            )
            geometry = getattr(capture.manifest, "receiver_geometry", None)
            supported = sum(v.state == "supported" for v in rows)
            manifest = RelativePhaseManifestV1(
                session_id=session_id,
                input_manifest_sha256=binding.input_manifest_sha256,
                glrt_binding_sha256=binding.sha256,
                binding_sha256=digest,
                state="not_applicable"
                if not applicable
                else "ready"
                if supported
                else "insufficient_signal",
                total_visit_count=len(indexes),
                selected_visits=selected,
                supported_visit_count=supported,
                pilot_checked_visit_count=sum(
                    v.evidence.get("pilot_held_rms_deg") is not None for v in rows
                ),
                receiver_geometry_digest=None
                if geometry is None
                else canonical_digest(geometry.model_dump(mode="json")),
                artifacts=tuple(
                    RelativePhaseArtifactV1(
                        name=name, sha256=sha256_digest(data), byte_count=len(data)
                    )
                    for name, data in images.items()
                ),
            )
            output.finalize(manifest, images)
            return dict(state="complete", manifest=manifest.model_dump(mode="json"))
    finally:
        analyses.close()
        captures.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--maximum-seconds", type=float, default=120)
    parser.add_argument("--probe-stride-ms", type=int, default=120)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.bulk_root,
                args.session_id,
                probe_stride_ms=args.probe_stride_ms,
                maximum_seconds=args.maximum_seconds,
            )
        )
    )


if __name__ == "__main__":
    main()
