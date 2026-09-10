#!/usr/bin/env python3
"""Read-only 24-hour scan export, preserving observations for paired RMS studies."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import explore_scan_edge_joins as edge
import numpy as np

from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories
from leo.application.persistent_hop_trajectory import project_fractional_persistent_hop_candidates
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_v2 import PersistentHopAnalysisStoreV2


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def export_scan(job: tuple[str, str, str]) -> dict:
    sid, bulk, output = job
    start = time.monotonic()
    root, dest = Path(bulk), Path(output)
    path = dest / "evidence" / f"{sid}.json"
    if path.exists():
        return json.loads(path.read_text())["inventory"]
    captures = PersistentHopIqStore.open_read_only(root)
    analyses = PersistentHopAnalysisStoreV2.open_read_only(root)
    capture, analysis = captures.inspect(sid), analyses.inspect(sid)
    manifest = capture.manifest
    summary = captures.history_item(sid)
    row = summary.model_dump(mode="json")
    row.update(
        manifest_sha256=capture.manifest_sha256,
        analysis_manifest_sha256=analysis.manifest_sha256,
        configuration=analysis.manifest.configuration.model_dump(mode="json"),
        reference_utc_ns=manifest.timing.first_sample_estimate_utc_ns,
        timing=manifest.timing.model_dump(mode="json"),
    )
    chunks = analyses.published_chunks(sid)
    row["analyzed_visits"] = sum(chunk.visit_count for chunk in chunks)
    row["included"] = summary.qualified and row["analyzed_visits"] == summary.visit_count
    if not row["included"]:
        write_json(path, {"inventory": row})
        return row
    projection = project_fractional_persistent_hop_candidates(
        manifest, chunks, input_manifest_sha256=capture.manifest_sha256
    )
    result = reconstruct_persistent_hop_trajectories(projection.candidates)
    by_id = {item.candidate_id: item for item in projection.candidates}
    raw = {
        (p.visit_index, p.receiver_id, p.probe_index, c.candidate_rank): c
        for ch in chunks
        for p in ch.probes
        for c in p.fractional_candidates
    }
    primary = set(result.hypotheses[0].tracklet_ids) if result.hypotheses else set()
    series, source = [], []
    for track in result.tracklets:
        if track.tracklet_id not in primary:
            continue
        candidates = [by_id[p.candidate_id] for p in track.points]
        originals = [
            raw[c.visit_index, c.receiver_id, c.probe_index, c.candidate_rank] for c in candidates
        ]
        times = np.array(
            [(c.support_center_utc_ns - row["reference_utc_ns"]) / 1e9 for c in candidates]
        )
        values = np.array([p.normalized_dealiased_cfo_hz for p in track.points])
        weights = np.array([min(c.margin / max(c.control_score, 0.02), 16) for c in candidates])
        series.append(
            edge.Series(
                track,
                times,
                values,
                weights,
                np.array([track.tracklet_id] * len(times), dtype=object),
            )
        )
        source.append(
            {
                "tracklet_id": track.tracklet_id,
                "channel": track.lane_key[0],
                "edge": track.lane_key[1].value,
                "receiver": track.lane_key[2],
                "actual_rf_hz": track.lane_key[3],
                "t_s": times.tolist(),
                "y_hz": values.tolist(),
                "weight": weights.tolist(),
                "observations": [
                    {**asdict(c), "persisted": o.model_dump(mode="json")}
                    for c, o in zip(candidates, originals, strict=True)
                ],
            }
        )
    tracks, accepted = edge._build_physical_tracks(series, edge._edge_candidates(series))
    episodes, replicas = edge._build_channel_episodes(tracks)
    joins = edge._switch_candidates(episodes)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(row["reference_utc_ns"] - 5_000_000_000, "space-track")
    payload = archive.read(snapshot)
    tle_name = f"catalogue-{snapshot.sha256}.tle"
    tle_path = dest / "evidence" / tle_name
    tle_path.parent.mkdir(parents=True, exist_ok=True)
    # Concurrent writers have the same digest-bound bytes; use exclusive creation.
    try:
        with tle_path.open("x") as stream:
            stream.write(payload)
    except FileExistsError:
        pass
    row.update(
        candidate_count=len(projection.candidates),
        probe_count=projection.input_probe_count,
        production_tracklet_count=len(result.tracklets),
        primary_tracklet_count=len(series),
        episode_count=len(episodes),
        receiver_merge_count=len(replicas),
        edge_merge_count=len(accepted),
        join_count=len(joins),
        tle_digest=snapshot.digest,
        tle_collected_ns=snapshot.collected_utc_ns,
        tle_file=tle_name,
    )
    document = {
        "inventory": row,
        "series": source,
        "episodes": [
            {
                "episode_id": e.episode_id,
                "label": e.label,
                "channel": e.channel,
                "support_s": [e.start_s, e.end_s],
                "members": [m.tracklet.tracklet_id for m in e.members],
            }
            for e in episodes
        ],
        "edge_merges": [edge._plain_edge(a) for a in accepted],
        "joins": [edge._plain_switch(j, rank) for rank, j in enumerate(joins, 1)],
    }
    write_json(path, document)
    print(
        f"{sid}: {len(series)} tracklets, {len(episodes)} episodes; "
        f"{time.monotonic() - start:.1f}s",
        flush=True,
    )
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-09-09T00:40:00+00:00")
    parser.add_argument("--end", default="2026-09-10T00:40:00+00:00")
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    captures = PersistentHopIqStore.open_read_only(args.bulk_root)
    start, end = datetime.fromisoformat(args.start), datetime.fromisoformat(args.end)
    selected = []
    for sid in captures.session_ids():
        summary = captures.history_item(sid)
        if start <= summary.captured_at < end:
            selected.append(summary)
    selected.sort(key=lambda row: row.captured_at)
    write_json(
        args.output / "frozen-cohort.json",
        {
            "start": args.start,
            "end": args.end,
            "sessions": [s.model_dump(mode="json") for s in selected],
            "source_commit": "39146ee83d00523fbd37ba02179c87a5c241a017",
            "selection_uses_signal_strength": False,
            "export_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
    )
    jobs = [(s.session_id, str(args.bulk_root), str(args.output)) for s in selected]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(export_scan, jobs))
    write_json(
        args.output / "inventory.json",
        {
            "start_utc": args.start,
            "end_utc": args.end,
            "extracted_at_utc": datetime.now(UTC).isoformat(),
            "scans": rows,
        },
    )


if __name__ == "__main__":
    main()
