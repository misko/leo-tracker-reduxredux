#!/usr/bin/env python3
"""Export a location-blind RF subset from the RX0 10 MS/s TLE review corpus."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def reference_utc_ns(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return round(parsed.timestamp() * 1_000_000_000)


def longest_track_per_lane(tracks: list[dict]) -> list[dict]:
    """Choose one RF track per channel/edge without consulting TLE scores."""
    selected: dict[tuple[int, str], dict] = {}
    for track in tracks:
        key = (int(track["channel"]), str(track["edge"]))
        rank = (
            float(track["span_s"]),
            int(track["observations"]),
            str(track["tracklet_id"]),
        )
        current = selected.get(key)
        if current is None:
            selected[key] = track
            continue
        current_rank = (
            float(current["span_s"]),
            int(current["observations"]),
            str(current["tracklet_id"]),
        )
        if rank > current_rank:
            selected[key] = track
    return [selected[key] for key in sorted(selected)]


def rf_document(record: dict, tle_name: str) -> dict:
    """Whitelist RF observations; deliberately omit known-site candidate fields."""
    series = []
    episodes = []
    for track in longest_track_per_lane(record["screen"]["tracks"]):
        tracklet_id = str(track["tracklet_id"])
        times = [float(value) for value in track["time_s"]]
        values = [float(value) for value in track["cfo_hz"]]
        if len(times) != len(values) or len(times) < 4:
            raise ValueError("invalid RF track arrays")
        series.append(
            {
                "tracklet_id": tracklet_id,
                "channel": int(track["channel"]),
                "edge": str(track["edge"]),
                "actual_rf_hz": 11_200_000_000.0,
                "t_s": times,
                "y_hz": values,
                "candidate_ids": [f"{tracklet_id}:{index}" for index in range(len(times))],
            }
        )
        episodes.append(
            {
                "episode_id": tracklet_id,
                "members": [tracklet_id],
                "channel": int(track["channel"]),
            }
        )
    screen = record["screen"]
    return {
        "inventory": {
            "session_id": record["session_id"],
            "reference_utc_ns": reference_utc_ns(record["capture_start_utc"]),
            "tle_file": tle_name,
            "tle_digest": screen["snapshot_digest"],
            "tle_collected_ns": int(screen["snapshot_collected_utc_ns"]),
            "sample_rate_hz": int(record["sample_rate_hz"]),
            "receiver_ids": normalized_receiver_ids(record["receiver_ids"]),
            "selection": "longest-track-per-channel-edge-by-span-observations-id-v1",
            "known_site_candidate_fields_used": False,
        },
        "series": series,
        "episodes": episodes,
    }


def normalized_receiver_ids(value: object) -> list[int]:
    if type(value) is int:
        return [value]
    if isinstance(value, str) and value.isdecimal():
        return [int(value)]
    if isinstance(value, list) and all(type(item) is int for item in value):
        return value
    raise ValueError("receiver IDs must be an integer or integer list")


def export(source: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("output must be fresh")
    output.mkdir(parents=True)
    evidence = output / "evidence"
    evidence.mkdir()
    records = sorted(
        (
            json.loads(gzip.decompress(path.read_bytes()))
            for path in source.glob("scan-hop-*.json.gz")
        ),
        key=lambda row: row["capture_start_utc"],
    )
    inventory = []
    copied: dict[str, str] = {}
    for record in records:
        if (
            int(record["sample_rate_hz"]) != 10_000_000
            or normalized_receiver_ids(record["receiver_ids"]) != [0]
            or record["radio_serial"] != "104000bac4950008230026001b440a003a"
        ):
            raise ValueError("cohort contains a recording outside the RX0 10 MS/s authority")
        screen = record["screen"]
        source_tle = Path(screen["snapshot_path"])
        tle_name = source_tle.name
        target_tle = evidence / tle_name
        expected = str(screen["snapshot_digest"])
        if tle_name not in copied:
            shutil.copyfile(source_tle, target_tle)
            actual = sha256(target_tle)
            if actual != expected:
                raise ValueError("catalogue digest mismatch")
            copied[tle_name] = actual
        elif copied[tle_name] != expected:
            raise ValueError("one catalogue filename has conflicting digests")
        document = rf_document(record, tle_name)
        path = evidence / f"{record['session_id']}.json"
        path.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
        inventory.append(
            {
                "session_id": record["session_id"],
                "reference_utc_ns": document["inventory"]["reference_utc_ns"],
                "included": True,
                "episode_count": len(document["episodes"]),
            }
        )
    (output / "inventory.json").write_text(
        json.dumps(
            {
                "schema": "org.leo.research.rx0-positioning-rf-export/v1",
                "source": str(source),
                "selection_uses_tle_or_known_location": False,
                "scans": inventory,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        f"Exported {len(inventory)} scans, {sum(row['episode_count'] for row in inventory)} "
        f"RF-only lane representatives, and {len(copied)} causal TLE snapshots"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.source, args.output)


if __name__ == "__main__":
    main()
