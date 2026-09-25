#!/usr/bin/env python3
"""Freeze the newest raw dwells with usable successful Standard V4 products."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from leo.acquisition.starlink_tuning import starlink_edge_rf_center_frequency_hz
from leo.contracts.standard_pipeline import resolve_manifest_starlink_tuning
from leo.pipeline.contracts import StageOutcome
from leo.storage import PinnedLocalRoot, RecordingStore

DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_COUNT = 50
DEFAULT_OUTPUT = Path("reports/figures/2026_08_24_recent_50_doppler/inputs.json")
SESSION_PATTERN = re.compile(r"^cap-\d{8}T\d{6}-[0-9a-f]{12}$")


@dataclass(frozen=True, slots=True)
class SuccessfulRun:
    session_id: str
    run_id: str
    pipeline_release_id: str
    maximum_job_id: int
    path_product_count: int
    analysis_manifest_digest: str


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def successful_runs(analysis_root: Path) -> tuple[SuccessfulRun, ...]:
    """Return the newest successful V4 run per syntactically valid capture session."""

    accepted = {outcome.value for outcome in StageOutcome}
    selected = []
    for session_root in analysis_root.glob("cap-*"):
        if not session_root.is_dir() or SESSION_PATTERN.fullmatch(session_root.name) is None:
            continue
        available = []
        for manifest_path in session_root.glob("*/manifest.json"):
            document = _load(manifest_path)
            jobs = document.get("jobs")
            if (
                document.get("session_id") != session_root.name
                or document.get("run_id") != manifest_path.parent.name
                or document.get("pipeline_lane") != "standard"
                or not isinstance(jobs, list)
                or not jobs
                or any(item.get("outcome") not in accepted for item in jobs)
            ):
                continue
            product_root = manifest_path.parent / "scientific" / "path-standard"
            path_count = sum(
                candidate.with_name("standard.pilot-scan.v3.json").is_file()
                for candidate in product_root.glob("*/standard.dealiased-trajectory-bank.v4.json")
            )
            if path_count < 1:
                continue
            available.append(
                SuccessfulRun(
                    session_id=session_root.name,
                    run_id=manifest_path.parent.name,
                    pipeline_release_id=str(document["pipeline_release_id"]),
                    maximum_job_id=max(int(item["job_id"]) for item in jobs),
                    path_product_count=path_count,
                    analysis_manifest_digest=_digest(manifest_path),
                )
            )
        if available:
            selected.append(max(available, key=lambda item: (item.maximum_job_id, item.run_id)))
    return tuple(sorted(selected, key=lambda item: item.session_id, reverse=True))


def _recording_fields(bundle: object) -> dict[str, object]:
    manifest = bundle.manifest
    tuning = resolve_manifest_starlink_tuning(manifest)
    if len(manifest.streams) != 2:
        raise ValueError("recent-50 Doppler cohort requires two-stream recordings")
    streams = []
    for stream in manifest.streams:
        settings = stream.applied_settings
        if settings.sample_rate_hz != 2_500_000 or stream.captured_sample_count <= 0:
            raise ValueError("recent-50 Doppler cohort requires committed 2.5 Msps streams")
        intent = tuning[stream.stream_id]
        first = stream.timing.first_sample
        streams.append(
            {
                "stream_id": stream.stream_id,
                "radio_id": stream.radio.radio_id,
                "sample_rate_hz": settings.sample_rate_hz,
                "sample_count": stream.captured_sample_count,
                "first_sample_estimate_utc_ns": first.estimate_utc_ns,
                "first_sample_earliest_utc_ns": first.earliest_utc_ns,
                "first_sample_latest_utc_ns": first.latest_utc_ns,
                "starlink_channel": intent.channel,
                "starlink_edge": intent.edge.value,
                "rf_center_frequency_hz": starlink_edge_rf_center_frequency_hz(
                    intent.channel, intent.edge
                ),
            }
        )
    return {
        "recording_manifest_digest": bundle.manifest_sha256,
        "recording_created_utc_ns": manifest.created_utc_ns,
        "recording_finalized_utc_ns": manifest.finalized_utc_ns,
        "streams": streams,
    }


def select_recent_dwells(bulk_root: Path, count: int) -> dict[str, object]:
    if count < 1:
        raise ValueError("recent dwell count must be positive")
    runs = successful_runs(bulk_root / "analysis")
    store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
    selected = []
    exclusions = []
    try:
        for run in runs:
            try:
                bundle = store.inspect(run.session_id)
                recording = _recording_fields(bundle)
            except (OSError, ValueError, RuntimeError) as error:
                exclusions.append(
                    {
                        "session_id": run.session_id,
                        "reason": f"{type(error).__name__}: {error}",
                    }
                )
                continue
            selected.append(
                {
                    "label": f"R{len(selected) + 1:02d}",
                    **asdict(run),
                    **recording,
                }
            )
            if len(selected) == count:
                break
    finally:
        store.close()
    if len(selected) != count:
        raise ValueError(f"only {len(selected)} eligible recent dwells were available")
    return {
        "schema": "org.leo.research.recent-raw-doppler-inputs/v1",
        "selection_algorithm": "newest-successful-standard-v4-readable-raw-v1",
        "requested_dwell_count": count,
        "selected_dwell_count": len(selected),
        "selection_order": "descending capture session ID",
        "run_selection": "largest successful terminal job ID, then run ID",
        "signal_strength_used_for_selection": False,
        "newest_session_id": selected[0]["session_id"],
        "oldest_session_id": selected[-1]["session_id"],
        "excluded_newer_candidates": exclusions,
        "dwells": selected,
    }


def main() -> None:
    arguments = _arguments()
    document = select_recent_dwells(arguments.bulk_root, arguments.count)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)


if __name__ == "__main__":
    main()
