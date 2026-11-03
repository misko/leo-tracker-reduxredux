"""Evaluate frozen adaptive-port products with the existing Graph/trimmed policy."""

import argparse
import hashlib
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import evaluate_ds22_merged_tracks as graph

from leo.analysis.research.public_tracking_points import public_tracking_points


def graph_rf_lanes(rows, source_id, config):
    """Never mix different actual RFs within a receiver/channel polynomial."""
    tracks, total = [], 0
    for frequency in sorted({r["actual_rf_hz"] for r in rows}):
        selected = [r for r in rows if r["actual_rf_hz"] == frequency]
        partial, count = graph.graph_tracks(selected, source_id, config)
        for track in partial:
            track["key"] += f"-RF{frequency:.6f}"
        tracks.extend(partial)
        total += count
    ids = [oid for t in tracks for oid in t["observation_ids"]]
    if len(ids) != len(set(ids)) or len(ids) != total:
        raise ValueError("RF lane split duplicated original point ownership")
    return tracks, total


def evaluate_case(entry, exports, output):
    source = exports / entry["source_id"] / "tracking.json"
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry["snapshot_sha256"]:
        raise ValueError("public input snapshot digest changed")
    document = json.loads(raw)
    if document["session_id"] != entry["session_id"]:
        raise ValueError("public snapshot has wrong capture identity")
    started = time.monotonic()
    rows, metadata = public_tracking_points(document)
    cfg = graph.TrackConfig(**json.loads(graph.CONFIG.read_text())["config"])
    tracks, count = graph_rf_lanes(rows, entry["source_id"], cfg)
    folder = output / entry["source_id"]
    folder.mkdir()
    graph.write(folder / "observations.json", rows)
    graph.write(folder / "tracks.json", tracks)
    if tracks:
        calibration, result = graph.merge_tracks(tracks)
        graph.write(folder / "merged.json", dict(calibration=calibration, result=result))
    else:
        result = dict(output_tracks=0, accepted_edges=[])
    receipt = dict(
        source_id=entry["source_id"],
        recording_id=entry["session_id"],
        status="tracks_evaluated",
        metadata=metadata,
        capture_utc_ns=metadata["anchor_utc_ns"],
        radio_id=document["radio_id"],
        input_manifest_sha256=document["input_manifest_sha256"],
        analysis_manifest_sha256=document["analysis_manifest_sha256"],
        raw_recording_authority_digest=document["raw_recording_authority_digest"],
        source_snapshot=str(source),
        source_sha256=entry["snapshot_sha256"],
        probes=len(document["probes"]),
        winning_points=len(rows),
        graph_points=count,
        graph_tracks=len(tracks),
        merged_tracks=result["output_tracks"],
        merge_edges=len(result["accepted_edges"]),
        elapsed_seconds=time.monotonic() - started,
        satellite_association="not_evaluated",
        position_error_km=None,
    )
    graph.write(folder / "receipt.json", receipt)
    return receipt


def run(exports, output, workers):
    output.mkdir(parents=True, exist_ok=False)
    coverage_path = exports / "coverage.json"
    entries = json.loads(coverage_path.read_text())
    if any(e["status"] == "pending" for e in entries):
        raise ValueError("wait for frozen export inventory before evaluating")
    source_paths = [
        Path(__file__),
        Path(graph.__file__),
        graph.ROOT / "src/leo/analysis/research/public_tracking_points.py",
    ]
    graph.write(
        output / "protocol.json",
        dict(
            export_protocol=json.loads((exports / "protocol.json").read_text()),
            export_coverage_sha256=hashlib.sha256(coverage_path.read_bytes()).hexdigest(),
            config_sha256=hashlib.sha256(graph.CONFIG.read_bytes()).hexdigest(),
            source_sha256={
                str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths
            },
            workers=workers,
            positions_used_in_track_construction=False,
            observations_withheld=0,
            lane_policy="receiver/channel/actual RF",
            dataset_mode="new adaptive snapshots",
        ),
    )
    ledger = {
        e["source_id"]: dict(
            source_id=e["source_id"],
            status="pending_analysis" if e["status"] == "exported" else e["status"],
        )
        for e in entries
    }
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(evaluate_case, entry, exports, output): entry["source_id"]
            for entry in entries
            if entry["status"] == "exported"
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = dict(
                    source_id=key, status="analysis_failed", reason=f"{type(exc).__name__}: {exc}"
                )
            ledger[key] = row
            graph.write(output / "coverage.json", [ledger[k] for k in sorted(ledger)])
            print(json.dumps({k: v for k, v in row.items() if k not in ("metadata",)}), flush=True)
    graph.write(output / "coverage.json", [ledger[k] for k in sorted(ledger)])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exports", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    qnap = Path("/mnt/qnap01")
    if a.output.resolve() == qnap or qnap in a.output.resolve().parents:
        p.error("QNAP is read-only")
    if a.workers < 1 or a.workers > 4:
        p.error("workers must be between one and four")
    run(a.exports, a.output, a.workers)
