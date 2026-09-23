"""Inventory fresh adaptive recordings using public capture metadata only.

This deliberately reads the immutable publication index and the public session
``capture`` summary.  It does not open a recording bundle, IQ, GLRT, tracks,
candidate caches, position outcomes, or reference coordinates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

from leo.storage.adaptive_hop import AdaptiveHopIqStore

OUT = Path(__file__).resolve().parent
BOUNDARY = datetime.fromisoformat("2026-09-23T16:35:28.398564+00:00")
GROUP_HOURS = 8
NOMINAL_DURATION_S = 300
WORKERS = 4
GEOMETRY_ROTATION_METADATA_LIMIT = " ".join(
    (
        "The public capture summary has no capture-bound geometry or orientation snapshot.",
        "geometry_authority_interval only says captured_at falls in one interval of the current",
        "released station-authority file; it does not verify the recording manifest or physical",
        "orientation, or Earth rotation. utc_qualified and its bracket describe capture-time",
        "metadata, not a rotation-validity certificate.",
    )
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def utc_group(start: datetime) -> datetime:
    return start.replace(
        hour=start.hour // GROUP_HOURS * GROUP_HOURS,
        minute=0,
        second=0,
        microsecond=0,
    )


def station_geometry_authorities() -> tuple[dict[str, object], ...]:
    """Read the released station authority, never a recording manifest."""
    source = OUT.parents[1] / "src/leo/station/gauss-r21-lt3d-001a-20260920-v1.json"
    values = json.loads(source.read_text())
    return (
        {
            "path": str(source.relative_to(OUT.parents[1])),
            "sha256": digest(source),
            "geometry_revision": values["geometry_revision"],
            "geometry_digest": values["geometry_digest"],
            "valid_from_utc_ns": values["valid_from_utc_ns"],
            "valid_until_utc_ns": values["valid_until_utc_ns"],
        },
    )


def geometry_interval_status(start: datetime, authorities: tuple[dict[str, object], ...]) -> str:
    start_ns = int(start.timestamp() * 1_000_000_000)
    matches = [
        value
        for value in authorities
        if value["valid_from_utc_ns"] <= start_ns < value["valid_until_utc_ns"]
    ]
    if len(matches) == 1:
        return "one_current_authority_interval"
    return "no_unique_current_authority_interval"


def capture_row(session_id: str, authorities: tuple[dict[str, object], ...]) -> dict[str, object]:
    try:
        with urlopen(
            f"http://127.0.0.1:8090/api/v3/scanner/adaptive-sessions/{session_id}", timeout=5
        ) as response:
            capture = json.load(response)["capture"]
        if capture["captured_at"] is None:
            return {"session_id": session_id, "state": "missing_captured_at"}
        start = parse_utc(capture["captured_at"])
        group = utc_group(start)
        duration = capture["nominal_duration_seconds"]
        contained = start + timedelta(seconds=duration) <= group + timedelta(hours=GROUP_HOURS)
        post_boundary = start > BOUNDARY
        completed_300 = capture["terminal_state"] == "completed" and duration == NOMINAL_DURATION_S
        return {
            "session_id": session_id,
            "state": "fresh_metadata" if post_boundary else "capture_not_after_boundary",
            "captured_at": start.isoformat(),
            "utc_8h_start": group.isoformat(),
            "nominal_duration_s": duration,
            "terminal_state": capture["terminal_state"],
            "completed_nominal_300s": completed_300,
            "contained_nominal_interval": contained,
            "sample_rate_hz": capture["sample_rate_hz"],
            "capture_qualified": capture["capture_qualified"],
            "utc_qualified": capture["utc_qualified"],
            "utc_bracket_width_ms": capture["utc_bracket_width_ms"],
            "source_span_attested": capture["source_span_attested"],
            "source_span_seconds": capture["source_span_seconds"],
            "geometry_authority_interval": geometry_interval_status(start, authorities),
            "input_manifest_sha256": capture["input_manifest_sha256"],
        }
    except Exception as error:
        return {
            "session_id": session_id,
            "state": "metadata_unavailable",
            "reason": type(error).__name__,
        }


def summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        if row["state"] == "fresh_metadata":
            grouped.setdefault(str(row["utc_8h_start"]), []).append(row)
    output = []
    for start, values in sorted(grouped.items()):
        completed = [value for value in values if value["completed_nominal_300s"]]
        rates: dict[str, int] = {}
        for value in completed:
            key = str(value["sample_rate_hz"])
            rates[key] = rates.get(key, 0) + 1
        output.append(
            {
                "utc_8h_start": start,
                "fresh_metadata_count": len(values),
                "completed_nominal_300s_count": len(completed),
                "completed_nominal_capture_seconds": sum(
                    int(value["nominal_duration_s"]) for value in completed
                ),
                "completed_nominal_300s_by_rate_hz": rates,
                "capture_qualified_count": sum(
                    bool(value["capture_qualified"]) for value in completed
                ),
                "utc_qualified_count": sum(bool(value["utc_qualified"]) for value in completed),
                "rows_with_one_current_geometry_authority_interval": sum(
                    value["geometry_authority_interval"] == "one_current_authority_interval"
                    for value in completed
                ),
                "session_ids": [
                    value["session_id"]
                    for value in sorted(values, key=lambda item: str(item["captured_at"]))
                ],
            }
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    queried_at = datetime.now(UTC)
    authorities = station_geometry_authorities()
    manifest = OUT.parent / "2026_09_23_long_inventory_complete/manifest.json"
    frozen = json.loads(manifest.read_text())
    frozen_ids = {
        session_id
        for partition in frozen["partitions"].values()
        for session_id in partition["session_ids"]
    }
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        indexed = sorted(
            {
                session_id
                for published_ns, session_id in store.publication_index()
                if published_ns > int(BOUNDARY.timestamp() * 1_000_000_000)
            }
        )
    finally:
        store.close()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        rows = list(pool.map(lambda session_id: capture_row(session_id, authorities), indexed))
    fresh = [row for row in rows if row["state"] == "fresh_metadata"]
    result = {
        "metadata_only": True,
        "forbidden_evidence_opened": {
            "recording_bundle_or_iq": False,
            "measurement_glrt_or_track_outcomes": False,
            "candidate_or_position_outcomes": False,
            "reference_coordinates": False,
        },
        "prospective_boundary_exclusive": BOUNDARY.isoformat(),
        "actual_query_utc": queried_at.isoformat(),
        "public_inventory": {
            "method": (
                "AdaptiveHopIqStore.publication_index read-only plus public capture summary API"
            ),
            "published_after_boundary_candidate_count": len(indexed),
            "candidate_ids": indexed,
        },
        "frozen_original_partitions": {
            "manifest_path": str(manifest.relative_to(OUT.parents[1])),
            "manifest_sha256": digest(manifest),
            "distinct_session_count": len(frozen_ids),
            "intersection_with_fresh_capture_ids": sorted(
                frozen_ids.intersection(row["session_id"] for row in fresh)
            ),
        },
        "station_geometry_authorities_current_repository": authorities,
        "geometry_rotation_metadata_limit": GEOMETRY_ROTATION_METADATA_LIMIT,
        "scan_rows": rows,
        "utc_8h_blocks": summary(rows),
        "accounting": {
            "fresh_capture_metadata_rows": len(fresh),
            "completed_nominal_300s_rows": sum(
                bool(row["completed_nominal_300s"]) for row in fresh
            ),
            "metadata_unavailable_rows": sum(
                row["state"] == "metadata_unavailable" for row in rows
            ),
            "capture_not_after_boundary_rows": sum(
                row["state"] == "capture_not_after_boundary" for row in rows
            ),
        },
        "worker_sha256": digest(Path(__file__)),
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
