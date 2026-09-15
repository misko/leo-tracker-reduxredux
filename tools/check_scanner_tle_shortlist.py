"""Covariance-aware audit of three exploratory shortlist examples; no RF."""

import argparse
import gzip
import json
from dataclasses import asdict
from pathlib import Path

from leo.analysis.persistent_hop_tle_match import (
    PersistentHopTleMatchConfig,
    match_persistent_hop_track_to_tles,
)
from leo.analysis.persistent_hop_trajectory import (
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from tools.publish_scanner_tle_review import concerns

AUDIT_RECORDINGS = (
    "scan-hop-24e4b051b0fbc5ca",
    "scan-hop-c2313aebc38416ef",
    "scan-hop-499abcb9ca352397",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == Path("/mnt/qnap01") or Path("/mnt/qnap01") in output.parents:
        parser.error("QNAP is read-only")
    output.mkdir(parents=True, exist_ok=True)
    records = sorted(
        (json.loads(p.read_text()) for p in args.source.glob("scan-hop-*.json")),
        key=lambda r: r["capture_start_utc"],
    )
    jobs = []
    for record in records:
        if record["session_id"] not in AUDIT_RECORDINGS:
            continue
        screen = record.get("screen")
        if not screen or not screen.get("exact_center_validation"):
            continue
        eligible = [t for t in screen["tracks"] if not concerns(t)]
        if eligible:
            jobs.append((record, max(eligible, key=lambda t: t["span_s"])))
        if len(jobs) == 3:
            break
    reader = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    try:
        for record, track in jobs:
            sid = record["session_id"]
            path = output / (sid + ".json.gz")
            if path.exists():
                continue
            screen = record["screen"]
            source = reader.load(sid)
            trajectory = reconstruct_persistent_hop_trajectories(project_scanner_candidates(source))
            hypothesis = next(
                h for h in trajectory.hypotheses if track["tracklet_id"] in h.tracklet_ids
            )
            graph = persistent_hop_tracklet_graph(hypothesis, track["tracklet_id"])
            snapshot = next(
                s for s in archive.list_snapshots() if s.digest == screen["snapshot_digest"]
            )
            records_tle = parse_element_set_records(archive.read(snapshot))
            excluded = {e["catalog_number"] for e in screen["exclusions"]}
            retained = [r for r in records_tle if r.satellite_number not in excluded]
            payload = "".join(r.text for r in retained)
            ref = TleSnapshotRefV1(
                provider=snapshot.provider,
                collected_utc_ns=snapshot.collected_utc_ns,
                digest=sha256_digest(payload.encode("ascii")),
                object_count=len(retained),
            )
            result = match_persistent_hop_track_to_tles(
                graph,
                payload,
                tle_snapshot=ref,
                observer_site=ObserverSiteV1.model_validate(screen["observer"]),
                config=PersistentHopTleMatchConfig(
                    selection_protocol_digest=canonical_digest(
                        {
                            "policy": "posthoc-three-earliest-recordings-longest-screen-pass",
                            "exclusions": screen["exclusions"],
                        }
                    ),
                    nominal_rf_hz=11_200_000_000.0,
                ),
            )
            evidence = {
                "session_id": sid,
                "tracklet_id": track["tracklet_id"],
                "selection": "three earliest screened recordings; "
                "longest descriptive-pass track in each; post-hoc audit",
                "original_snapshot_digest": snapshot.digest,
                "exclusions": screen["exclusions"],
                "screen_leader": track["fields"]["0"]["top_training"][0]["catalog_number"],
                "result": asdict(result),
            }
            path.write_bytes(gzip.compress(json.dumps(evidence).encode(), mtime=0))
            print(
                json.dumps(
                    {
                        "session": sid,
                        "leader": result.leading_catalog_number,
                        "reasons": result.abstention_reasons,
                    }
                ),
                flush=True,
            )
    finally:
        reader.close()


if __name__ == "__main__":
    main()
