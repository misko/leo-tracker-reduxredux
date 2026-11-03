"""Resume a bounded search from hash-verified objective evaluations.

The original uniform regional search is replayed exactly. Cached evaluations
save work without changing its budget, basin selection or final calibration.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import search_merged_track_position as search
from associate_merged_track_catalogue import write
from localize_merged_track_catalogue import distance_km


def replay_objective(objective, progress):
    cache = {}
    for row in progress:
        if not row["final"]:
            key = tuple(np.round(row["east_north_km"], 9))
            if key in cache and cache[key] != row["score"]:
                raise ValueError("conflicting cached objective values")
            cache[key] = row["score"]

    def replay(point):
        key = tuple(np.round(point, 9))
        return cache[key] if key in cache else objective(point)

    return replay


def run(previous, recording, inputs, output):
    protocol_path, progress_path = previous / "protocol.json", previous / "progress.json"
    protocol = json.loads(protocol_path.read_text())
    for name, digest in protocol["source_sha256"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError("scientific source changed; cached scores cannot be reused")
    for path, expected in (
        (inputs / "bank.npz", protocol["bank_sha256"]),
        (recording / "tracks.json", protocol["tracks_sha256"]),
        (recording / "merged.json", protocol["merged_sha256"]),
    ):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("scientific inputs changed; cached scores cannot be reused")
    if (previous / "fit.json").exists():
        raise ValueError("previous search already completed")
    progress = json.loads(progress_path.read_text())
    regional = search.regional_search

    def resumed(objective, **kwargs):
        return regional(replay_objective(objective, progress), **kwargs)

    search.regional_search = resumed
    try:
        result = search.run(
            recording, inputs, output, protocol["fitted_c"], grouping=protocol["grouping"]
        )
    finally:
        search.regional_search = regional
    write(
        output / "resume-receipt.json",
        dict(
            previous=str(previous),
            previous_protocol_sha256=hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
            previous_progress_sha256=hashlib.sha256(progress_path.read_bytes()).hexdigest(),
            cached_discovery_evaluations=sum(not row["final"] for row in progress),
            original_search_policy_replayed=True,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--previous", type=Path, required=True)
    p.add_argument("--recording", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--evaluation-latitude", type=float, required=True)
    p.add_argument("--evaluation-longitude", type=float, required=True)
    a = p.parse_args()
    fit = run(a.previous, a.recording, a.inputs, a.output)
    endpoint = fit["endpoint"]
    error = distance_km(
        endpoint["latitude_deg"],
        endpoint["longitude_deg"],
        a.evaluation_latitude,
        a.evaluation_longitude,
    )
    write(
        a.output / "evaluation.json",
        dict(
            position_error_km=error,
            within_0_5km=error < 0.5,
            reference_used_only_after_fit=True,
            goal_complete=False,
            fit_sha256=hashlib.sha256((a.output / "fit.json").read_bytes()).hexdigest(),
        ),
    )
    print(json.dumps(dict(position_error_km=error)), flush=True)
