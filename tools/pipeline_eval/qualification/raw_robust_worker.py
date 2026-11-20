"""Run only the frozen anonymous observation and graph preparation stage."""

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time

TRACK_FIELDS = ("times", "values", "receiver", "channel", "rf_hz")


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def checked_json(record):
    raw = Path(record["path"]).read_bytes()
    if sha256(raw).hexdigest() != record["sha256"]:
        raise ValueError("track preparation input changed after it was bound")
    return json.loads(raw)


def anonymous(prepared, cutoff, catalogue_timestamp):
    metadata = prepared["metadata"]
    if metadata["causal_cutoff_utc_ns"] != cutoff or catalogue_timestamp > cutoff:
        raise ValueError("track timing or catalogue is outside capture authority")
    return dict(
        anchor_utc_ns=metadata["anchor_utc_ns"],
        cutoff_utc_ns=cutoff,
        duration_s=metadata["duration_s"],
        catalog_timestamp_ns=catalogue_timestamp,
        tracks=[
            {
                key: track[key].tolist() if key in ("times", "values") else track[key]
                for key in TRACK_FIELDS
            }
            for track in prepared["tracks"]
        ],
    )


def worker(request, frozen):
    from leo.analysis.localization_v3 import tracks

    from leo.analysis import polynomial_tracklets

    if not all(
        Path(module.__file__).resolve().is_relative_to(frozen)
        for module in (tracks, polynomial_tracklets)
    ):
        raise ValueError("load the frozen numerical tracker implementation")
    read_start, read_cpu = perf_counter(), process_time()
    document = checked_json(request["native"])
    config = checked_json(request["track_config"])
    source = document["source"]
    if (
        source["session_id"] != request["session_id"]
        or not source["qualified"]
        or source["capture_mode"] != "adaptive"
        or source["sample_rate_hz"] != 10_000_000
        or source["probe_ms"] != 20
        or document["provenance"]["window_count"] != request["window_count"]
    ):
        raise ValueError("detector input is outside the qualified whole-recording geometry")
    read = dict(wall_s=perf_counter() - read_start, cpu_s=process_time() - read_cpu)
    started, cpu = perf_counter(), process_time()
    prepared = tracks.prepare_tracks(document, polynomial_tracklets.TrackConfig(**config["config"]))
    elapsed = dict(wall_s=perf_counter() - started, cpu_s=process_time() - cpu)
    projection = anonymous(prepared, request["cutoff_utc_ns"], request["catalog_timestamp_ns"])
    return dict(
        projection=projection,
        authority=dict(
            input_manifest_sha256=source["input_manifest_sha256"],
            raw_recording_authority_digest=source["raw_recording_authority_digest"],
            window_count=document["provenance"]["window_count"],
            excluded_visits_sha256=digest(document["provenance"]["excluded_windows"]),
            clock_sha256=digest(
                [document[k] for k in ("clock_anchor", "delivery_clocks", "last_sample_counter")]
            ),
            probe_support_sha256=digest(
                [
                    {key: value for key, value in probe.items() if key != "candidates"}
                    for probe in source["probes"]
                ]
            ),
        ),
        metrics=dict(
            detector_decode=read,
            tracker=elapsed,
            track_peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
            graph_status=prepared["status"],
            tracks=len(prepared["tracks"]),
            selected_glrt_observations=len(prepared["observations"]),
            graph_assigned_observations=prepared["graph_points"],
            active_curvature_tracks=len(prepared["curved_indices"]),
            clock_half_width_s=prepared["metadata"]["utc_half_width_s"],
        ),
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--frozen", required=True, type=Path)
    args = cli.parse_args()
    json.dump(
        worker(json.load(sys.stdin), args.frozen.resolve()),
        sys.stdout,
        allow_nan=False,
        separators=(",", ":"),
    )


if __name__ == "__main__":
    main()
