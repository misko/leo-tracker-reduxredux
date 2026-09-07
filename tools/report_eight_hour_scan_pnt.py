#!/usr/bin/env python3
"""Bounded retrospective experiment over sealed scanner products; read-only adapters."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import explore_scan_edge_joins as edge
import numpy as np

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.persistent_hop_trajectory import project_fractional_persistent_hop_candidates
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_v2 import PersistentHopAnalysisStoreV2


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def epoch_ns(text: str) -> int:
    return round(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1e9)


def extract(args: argparse.Namespace) -> None:
    captures = PersistentHopIqStore.open_read_only(args.bulk_root)
    analyses = PersistentHopAnalysisStoreV2.open_read_only(args.bulk_root)
    archive = TleArchiveReader(args.tle_root)
    start_ns, end_ns = epoch_ns(args.start), epoch_ns(args.end)
    inventory = []
    selected = []
    for session_id in captures.session_ids():
        summary = captures.history_item(session_id)
        created_ns = round(summary.captured_at.timestamp() * 1e9)
        if start_ns <= created_ns < end_ns:
            selected.append(summary)
    for index, summary in enumerate(sorted(selected, key=lambda row: row.captured_at)):
        dest = args.output / "evidence" / f"{summary.session_id}.json"
        if dest.exists():
            document = json.loads(dest.read_text())
            inventory.append(document["inventory"])
            print(f"cached {index + 1}/{len(selected)} {summary.session_id}", flush=True)
            continue
        capture = captures.inspect(summary.session_id)
        manifest = capture.manifest
        chunks = analyses.published_chunks(summary.session_id)
        row = summary.model_dump(mode="json")
        row["manifest_sha256"] = capture.manifest_sha256
        row["analyzed_visits"] = sum(chunk.visit_count for chunk in chunks)
        row["chunk_count"] = len(chunks)
        row["reference_utc_ns"] = manifest.timing.first_sample_estimate_utc_ns
        row["timing"] = manifest.timing.model_dump(mode="json")
        if not summary.qualified or row["analyzed_visits"] != summary.visit_count:
            row["included"] = False
            row["reason"] = "unqualified capture or incomplete fractional analysis"
            inventory.append(row)
            print(f"exclude {summary.session_id}: {row['reason']}", flush=True)
            continue
        projection = project_fractional_persistent_hop_candidates(
            manifest, chunks, input_manifest_sha256=capture.manifest_sha256
        )
        result = reconstruct_persistent_hop_trajectories(
            projection.candidates, config=PersistentHopTrajectoryConfig()
        )
        primary_ids = set(result.hypotheses[0].tracklet_ids) if result.hypotheses else set()
        by_id = {item.candidate_id: item for item in projection.candidates}
        series, source_rows = [], []
        for track in result.tracklets:
            if track.tracklet_id not in primary_ids:
                continue
            candidates = [by_id[point.candidate_id] for point in track.points]
            times = np.array(
                [
                    (item.support_center_utc_ns - row["reference_utc_ns"]) / 1e9
                    for item in candidates
                ]
            )
            values = np.array([point.normalized_dealiased_cfo_hz for point in track.points])
            weights = np.array(
                [
                    min(max(item.margin, 0) / max(item.control_score, 0.02), 16)
                    for item in candidates
                ]
            )
            series.append(
                edge.Series(
                    track,
                    times,
                    values,
                    weights,
                    np.array([track.tracklet_id] * len(times), dtype=object),
                )
            )
            source_rows.append(
                {
                    "tracklet_id": track.tracklet_id,
                    "channel": track.lane_key[0],
                    "edge": track.lane_key[1].value,
                    "receiver": track.lane_key[2],
                    "actual_rf_hz": track.lane_key[3],
                    "t_s": times.tolist(),
                    "y_hz": values.tolist(),
                    "weight": weights.tolist(),
                    "candidate_ids": [item.candidate_id for item in candidates],
                }
            )
        tracks, accepted = edge._build_physical_tracks(series, edge._edge_candidates(series))
        episodes, replicas = edge._build_channel_episodes(tracks)
        joins = edge._switch_candidates(episodes)
        snapshot = archive.select_latest_before(
            row["reference_utc_ns"] - 5_000_000_000, "space-track"
        )
        payload = archive.read(snapshot)
        tle_path = args.output / "evidence" / f"catalogue-{snapshot.sha256}.tle"
        tle_path.parent.mkdir(parents=True, exist_ok=True)
        tle_path.write_text(payload)
        row.update(
            {
                "included": True,
                "candidate_count": len(projection.candidates),
                "production_tracklet_count": len(result.tracklets),
                "primary_tracklet_count": len(series),
                "physical_track_count": len(tracks),
                "episode_count": len(episodes),
                "receiver_merge_count": len(replicas),
                "edge_merge_count": len(accepted),
                "join_count": len(joins),
                "tle_digest": snapshot.digest,
                "tle_collected_ns": snapshot.collected_utc_ns,
                "tle_file": tle_path.name,
            }
        )
        document = {
            "inventory": row,
            "series": source_rows,
            "episodes": [
                {
                    "episode_id": episode.episode_id,
                    "label": episode.label,
                    "channel": episode.channel,
                    "support_s": [episode.start_s, episode.end_s],
                    "members": [member.tracklet.tracklet_id for member in episode.members],
                }
                for episode in episodes
            ],
            "edge_merges": [edge._plain_edge(item) for item in accepted],
            "joins": [edge._plain_switch(item, rank) for rank, item in enumerate(joins, 1)],
        }
        write_json(dest, document)
        inventory.append(row)
        print(
            f"extracted {index + 1}/{len(selected)} {summary.session_id}: "
            f"{len(series)} tracks -> {len(episodes)} episodes",
            flush=True,
        )
    write_json(
        args.output / "inventory.json",
        {
            "schema_version": 1,
            "start_utc": args.start,
            "end_utc": args.end,
            "extracted_at_utc": datetime.now(UTC).isoformat(),
            "scans": inventory,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-09-07T07:49:15Z")
    parser.add_argument("--end", default="2026-09-07T15:49:15Z")
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    extract(args)


if __name__ == "__main__":
    main()
