"""Recover exact curved epoch widths from sealed successor detections alone."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from compact_rank_scope_audit import CASES, summarize
from curved_rank_time import time_union
from empty_bootstrap import RELEASE, checked, load_runtime
from exact_graph_execution import graph_execution


CONFIG_SHA = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"


def inspect(attempt, config):
    from leo.analysis.localization_v3.tracks import prepare_tracks

    scope = summarize(attempt)
    result = json.loads((attempt/"result.json").read_bytes())
    publication = attempt/"publication"
    paths = list(publication.glob("fast-scan-automatic-work/*/detections.json"))
    if len(paths) != 1:
        raise ValueError("The original successor has no unique detector packet")
    raw = paths[0].read_bytes()
    digest = "sha256:" + sha256(raw).hexdigest()
    if digest != result["native_sha256"]:
        raise ValueError("The retained receiver packet is not the sealed field input")
    with graph_execution(enabled=True):
        prepared = prepare_tracks(json.loads(raw), config)
    tracks, curved = prepared["tracks"], prepared["curved_indices"]
    times = np.unique(np.concatenate([track["times"] for track in tracks]))
    indexes = [np.searchsorted(times, track["times"]) for track in tracks]
    curved_points = sum(len(indexes[i]) for i in curved)
    if (len(times), len(curved), len(tracks), curved_points, prepared["graph_points"]) != (
            scope["projection_axis_epochs"], scope["curved_tracks"], scope["graph_tracks"],
            scope["curved_points"], scope["graph_points"]):
        raise ValueError("The released Graph reconstruction differs from the paid rank counters")
    columns = time_union(times, indexes, curved)
    removed = len(times) - len(columns)
    return dict(native_sha256=digest, graph_points=prepared["graph_points"],
                graph_tracks=len(tracks), curved_tracks=len(curved), curved_points=curved_points,
                epochs=len(times), curved_only_epochs=len(np.unique(np.concatenate([indexes[i] for i in curved]))),
                retained_epochs=len(columns), removed_epochs=removed, removed_fraction=removed/len(times),
                projected_planar_bytes_avoided=removed*scope["catalogue_rows"]*3*8,
                all_rank_cpu_s=scope["rank_cpu_ns"]/1e9, checks=scope["receipt_sha256"])


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("campaign", type=Path)
    args = cli.parse_args()
    load_runtime()
    from leo.analysis.polynomial_tracklets import TrackConfig

    config = TrackConfig(**json.loads(checked(RELEASE/"assets/tracks.json", CONFIG_SHA))["config"])
    cases = {case: inspect(args.campaign/"cases"/case/"successor/attempt-000001", config) for case in CASES}
    print(json.dumps(dict(cases=cases, waveform_reads=0, ranks=0, orbit_reads=0, schema_version=1),
                     indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
