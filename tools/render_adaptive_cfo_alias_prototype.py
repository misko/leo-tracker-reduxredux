"""Publish an additive comparison from one sealed scan; no acquisition or re-analysis."""

import argparse
import json
from pathlib import Path

import numpy as np

from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.digests import sha256_digest
from leo.presentation.adaptive_cfo_alias import render_adaptive_cfo_alias_context
from leo.presentation.adaptive_hop_analysis import project_adaptive_overview
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.scanner_tracking import ScannerTrackingStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def audit_wrap(root: Path, session_id: str, output: Path):
    """Replay only CH4 RX0 candidate associations with production defaults."""
    inputs = ScannerTrackingInputStore(root)
    try:
        source = inputs.load(session_id)
    finally:
        inputs.close()
    candidates = tuple(
        c for c in project_scanner_candidates(source) if c.channel == 4 and c.receiver_id == 0
    )
    result = reconstruct_persistent_hop_trajectories(candidates)
    origin = source.timing.first_sample_estimate_utc_ns
    by_id = {c.candidate_id: c for c in candidates}
    tracklets = []
    for track in result.tracklets:
        start, end = (track.start_utc_ns - origin) / 1e9, (track.end_utc_ns - origin) / 1e9
        if start >= 205 or end <= 190:
            continue
        points = []
        for point in track.points:
            candidate = by_id[point.candidate_id]
            time_s = (candidate.support_center_utc_ns - origin) / 1e9
            if 197 < time_s < 201:
                points.append(
                    dict(
                        time_s=time_s,
                        alias_index=point.relative_alias_index,
                        normalized_raw_hz=point.normalized_raw_cfo_hz,
                        normalized_dealiased_hz=point.normalized_dealiased_cfo_hz,
                    )
                )
        tracklets.append(
            dict(tracklet_id=track.tracklet_id, start_s=start, end_s=end, points_near_wrap=points)
        )
    evidence = dict(
        candidate_count=len(candidates),
        tracklets=tracklets,
        scope="CH4 RX0 only; production reconstruction defaults, no IQ or TLE matching",
    )
    (output / "wrap-audit.json").write_text(json.dumps(evidence, indent=2) + "\n")


def render(root: Path, session_id: str, output: Path):
    captures = AdaptiveHopIqStore(root, read_only=True)
    products = AdaptiveHopAnalysisStore(root, read_only=True)
    try:
        capture = captures.inspect(session_id)
        binding = bind_actual_visit_analysis(
            capture.manifest.receipt,
            input_manifest_sha256=capture.manifest_sha256,
            probe_stride_ms=120,
        )
        with products.job(binding) as job:
            metrics, overview = job.manifest(), job.overview()
            if metrics is None or overview is None:
                raise ValueError("Prototype requires sealed metrics and an existing overview")
            reference = next(a for a in overview.artifacts if a.name == "cfo-trajectories")
            original = job.read_artifact(reference.name, expected_sha256=reference.sha256)
            if original is None:
                raise ValueError("Original overview PNG missing")
            visits = tuple(job.published_visits())
        figures = render_adaptive_cfo_alias_context(binding, metrics, visits)
        figures["cfo-original"] = original
        output.mkdir(parents=True, exist_ok=False)
        for name, payload in figures.items():
            (output / f"{name}.png").write_bytes(payload)
        data = project_adaptive_overview(binding, metrics, visits)
        np.savetxt(
            output / "canonical-candidates.csv",
            data.passed,
            delimiter=",",
            header="target,receiver,time_s,cfo_hz",
            comments="",
        )
        status = ScannerTrackingStore(root).status(session_id)
        product = status.product
        receipt = {
            "session_id": session_id,
            "input_manifest_sha256": capture.manifest_sha256,
            "metrics_manifest_sha256": overview.metrics_manifest_sha256,
            "canonical_candidate_count": len(data.passed),
            "alias_context_hz": 100_000,
            "artifacts": {name: sha256_digest(payload) for name, payload in figures.items()},
            "tracking_state": status.state,
            "tracking": product.model_dump(mode="json") if product else None,
            "capture_start_utc_ns": capture.manifest.timing.first_sample_estimate_utc_ns,
        }
        (output / "evidence.json").write_text(json.dumps(receipt, indent=2) + "\n")
        html = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CFO alias context — {session_id}</title>
<style>body{{font:16px system-ui;max-width:1500px;margin:2rem auto;padding:0 1rem;color:#172033}}
img{{width:100%;height:auto}}a{{color:#126190}}p{{max-width:1000px}}</style>
<h1>CFO alias context</h1><p>{session_id}</p>
<p>The alias period is 227.273 kHz. The companion view adds 100 kHz above and below
the canonical ±113.636 kHz interval. Shaded points are exact shifted copies of existing
candidates, not additional detections or independent evidence. No IQ was re-analyzed.</p>
<p>The downstream Hough tracker uses modulo-alias residuals. The dashed lines in these
overview PNGs use a separate polynomial fitter and are not downstream track IDs.
Visual continuity supports a wrap hypothesis but does not establish satellite identity.</p>
<h2>Original published PNG</h2><a href="cfo-original.png">
<img src="cfo-original.png" alt="Original CFO candidates"></a>
<h2>Companion: 100 kHz alias context</h2><a href="cfo-alias-context.png">
<img src="cfo-alias-context.png" alt="CFO candidates and adjacent aliases"></a>
<h2>Channel 4, 180–230 seconds</h2><a href="ch4-wrap-zoom.png">
<img src="ch4-wrap-zoom.png" alt="Channel 4 wrap detail"></a>
<p><a href="evidence.json">Source digests and saved tracking evidence</a> ·
<a href="canonical-candidates.csv">Canonical candidates</a></p></html>"""
        (output / "index.html").write_text(html)
        print(
            json.dumps(
                {
                    "output": str(output),
                    "candidates": len(data.passed),
                    "tracking_state": status.state,
                }
            )
        )
    finally:
        products.close()
        captures.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id")
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-wrap", action="store_true")
    args = parser.parse_args()
    render(args.bulk_root, args.session_id, args.output)
    if args.audit_wrap:
        audit_wrap(args.bulk_root, args.session_id, args.output)
