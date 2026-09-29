"""Read-only metadata/API audit; never reads IQ or starts processing."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore

ROOT = Path(__file__).resolve().parent
WORKER = Path("/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc")
API = Path("/opt/leo-tracker/current-api").resolve()
SESSIONS = (
    "scan-fw-ca88edc9307953b1",
    "scan-fw-685d045965fa924b",
    "scan-fw-d479435ef17109f8",
    "scan-fw-6376718c921309b1",
)


def get(route):
    with urlopen("http://127.0.0.1:8090" + route, timeout=20) as response:
        return json.load(response)


def main():
    evidence = dict(observed_utc=datetime.now(UTC).isoformat(), worker=str(WORKER),
                    api=str(API), sessions=[], source_hashes={})
    for release in (WORKER, API):
        for name in (
            "src/leo/cli/adaptive_processing_queue.py",
            "src/leo/cli/adaptive_hop_analysis.py",
            "src/leo/cli/adaptive_relative_phase.py",
            "src/leo/scanner/adaptive_hop_analysis.py",
            "src/leo/scanner/detector.py",
            "src/leo/storage/scanner_tracking_source.py",
            "web/src/AdaptiveAnalysisPanel.tsx",
            "web/src/AdaptiveRelativePhase.tsx",
        ):
            p = release / name
            evidence["source_hashes"][str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    products = AdaptiveHopAnalysisStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        for sid in SESSIONS:
            capture = store.inspect(sid)
            receipt = capture.manifest.receipt
            geometry = receipt.plan.geometry
            row = dict(session_id=sid, raw_digest=capture.manifest_sha256,
                       sample_rate_hz=geometry.sample_rate_hz,
                       geometry=geometry.model_dump(mode="json"),
                       actual_dwell_counts=dict(Counter(
                           str((v.valid_end_counter_exclusive - v.valid_start_counter)
                               * 1000 / geometry.sample_rate_hz) for v in receipt.events)),
                       analysis={}, png_checks=[])
            base = f"/api/v2/scanner/adaptive-sessions/{sid}/analysis"
            for stride in (10, 20, 120):
                status = get(base + f"?probe_stride_ms={stride}")
                row["analysis"][str(stride)] = status
            binding = bind_actual_visit_analysis(receipt,
                input_manifest_sha256=capture.manifest_sha256, probe_stride_ms=120)
            with products.job(binding) as job:
                indexes = job.completed_visits()
                row["sampled_products"] = []
                wanted = {}
                for v in receipt.events:
                    dwell = (v.valid_end_counter_exclusive - v.valid_start_counter)
                    if v.visit_index in indexes:
                        wanted.setdefault(dwell, v.visit_index)
                for index in wanted.values():
                    visit = job.read_visit(index)
                    row["sampled_products"].append(dict(visit_index=index,
                        valid_samples=visit.valid_end_counter-visit.valid_start_counter,
                        probe_ms=visit.configuration.probe_ms,
                        stride_ms=visit.configuration.probe_stride_ms,
                        starts_ms=sorted({p.probe_start_ms for p in visit.probes}),
                        probe_records=len(visit.probes)))
            phase_base = f"/api/v1/scanner/adaptive-sessions/{sid}/analysis/relative-phase"
            phase = get(phase_base + "?probe_stride_ms=120")
            row["relative_phase"] = phase
            tracking = get(f"/api/v1/scanner/tracking/{sid}")
            product = tracking.get("product") or {}
            row["tracking"] = dict(state=tracking["state"], product={k: product.get(k) for k in (
                "input_manifest_sha256", "analysis_manifest_sha256", "created_at",
                "trajectory_state", "tle_state", "artifacts")})
            status = row["analysis"]["120"]
            for stage, manifest, route, digest in (
                ("glrt", status.get("overview"), base, status["binding_sha256"]),
                ("relative_phase", phase.get("manifest"), phase_base,
                 phase["binding_sha256"]),
            ):
                for artifact in (manifest or {}).get("artifacts", []):
                    query = urlencode(dict(probe_stride_ms=120, binding_sha256=digest,
                                           artifact_sha256=artifact["sha256"]))
                    url = route + "/" + artifact["name"] + ".png?" + query
                    with urlopen("http://127.0.0.1:8090" + url, timeout=20) as response:
                        payload = response.read()
                        row["png_checks"].append(dict(stage=stage, name=artifact["name"],
                            http_status=response.status, content_type=response.headers.get_content_type(),
                            png_signature=payload.startswith(b"\x89PNG\r\n\x1a\n"),
                            bytes_match=len(payload) == artifact["byte_count"],
                            digest_match="sha256:"+hashlib.sha256(payload).hexdigest()==artifact["sha256"]))
            evidence["sessions"].append(row)
            print(sid, row["actual_dwell_counts"],
                  {s: v["state"] for s, v in row["analysis"].items()}, flush=True)
    finally:
        store.close()
    evidence["finished_utc"] = datetime.now(UTC).isoformat()
    (ROOT / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    main()
