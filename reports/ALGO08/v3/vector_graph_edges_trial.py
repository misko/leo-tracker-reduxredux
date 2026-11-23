"""Measure ordered graph construction through the installed native path finder."""

import argparse
import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np
from aperture_trial import RELEASE, configuration, write
from dense_geographic_trial import host
from local_future_policy import TRACKS_SHA256
from vector_graph_edges import ordered_edges

CASES = {
    "dense": (
        "/var/tmp/leo-v3-regional-dense-pair/native",
        "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85",
    ),
    "weak": (
        "/dev/shm/leo-unified-short-layout.lDeYMN5U/trial/weak/candidate",
        "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589",
    ),
    "north": (
        "/var/tmp/leo-north-short-regional-nov23/containing",
        "2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427",
    ),
}


def fingerprint(tracks):
    from leo.application.localization_v3_engine import _json_value

    data = json.dumps(
        tracks, default=_json_value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return sha256(data).hexdigest()


def compare_edges(original, candidate):
    for old, new in zip(original[:4], candidate[:4], strict=True):
        if old.dtype != new.dtype or old.shape != new.shape or old.tobytes() != new.tobytes():
            raise ValueError("Ordered edge array changed")
    for before, after in zip(original[4:], candidate[4:], strict=True):
        for old, new in zip(before, after, strict=True):
            if old.dtype != new.dtype or not np.array_equal(old, new):
                raise ValueError("Ordered adjacency changed")


def run(output):
    from leo.analysis import graph_tracklets as graph
    from leo.analysis.localization_v3.tracks import graph_tracks, winning_observations
    from leo.analysis.polynomial_tracklets import TrackConfig
    from tools.pipeline_eval.variants.experimental.graph_path import native_paths

    machine = host()
    publication, spec = configuration()
    publication._checked_graph_path(spec)
    asset = (RELEASE / "assets/tracks.json").read_bytes()
    if sha256(asset).hexdigest() != TRACKS_SHA256:
        raise ValueError("Unknown graph configuration")
    config = TrackConfig(**json.loads(asset)["config"])
    original = graph._graph
    data = {}
    for case, (root, pin) in CASES.items():
        (source,) = Path(root).glob("fast-scan-automatic-work/*/detections.json")
        payload = source.read_bytes()
        if sha256(payload).hexdigest() != pin:
            raise ValueError(f"Unknown receiver packet for {case}")
        observations = winning_observations(json.loads(payload))[0]
        rows = []
        for mode in ("verify", "original", "vector", "vector", "original"):
            edge_cpu, fallback, lanes, edges = 0.0, 0, 0, 0

            def stock(*args):
                nonlocal fallback
                fallback += 1
                return original(*args)

            def build(t, y, cfg, *, mode=mode):
                nonlocal edge_cpu, lanes, edges
                start = process_time()
                result = (
                    original(t, y, cfg) if mode == "original" else ordered_edges(t, y, cfg, stock)
                )
                edge_cpu += process_time() - start
                if mode == "verify":
                    compare_edges(original(t, y, cfg), result)
                edges += len(result[0])
                lanes += 1
                return result

            with (
                native_paths(Path(spec["graph_path"]["library"]), required=True) as native,
                patch.object(graph, "_graph", build),
            ):
                cpu, wall = process_time(), perf_counter()
                tracks, assigned = graph_tracks(observations, config)
                cpu, wall = process_time() - cpu, perf_counter() - wall
            rows.append(
                dict(
                    mode=mode,
                    edge_cpu_s=edge_cpu,
                    graph_cpu_s=cpu,
                    graph_elapsed_s=wall,
                    graph_sha256=fingerprint(tracks),
                    assigned=assigned,
                    lanes=lanes,
                    edges=edges,
                    fallback=fallback,
                    native=dict(native),
                )
            )
        if len({r["graph_sha256"] for r in rows}) != 1 or any(r["fallback"] for r in rows):
            raise ValueError("Saved track descriptions differ or the fallback ran")
        data[case] = dict(packet_sha256=pin, observations=len(observations), runs=rows)
    write(output, dict(machine=machine, graph_config_sha256=TRACKS_SHA256, cases=data))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
