"""Audit a solver boundary gate and verify causal scores on saved detections."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import process_time

from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.localization_v3.tracks import prepare_tracks
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.application.localization_v3_engine import _json_value
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from regional_exterior_veto_trial import MEASUREMENTS, saved_offers
from tools.pipeline_eval.variants.experimental.regional_bound_guard import (
    ARMS, causal_probes, inspect_boundary,
)


def region_key(region):
    return tuple(region["center"]), region["width_km"]


def path_evidence(path, grid):
    if (
        path is None or grid is None or path["region_center"] != grid["region_center"]
        or path["box_width_km"] != grid["box_width_km"]
    ):
        return None
    arms = path["stages"][-1]["arms"]
    endpoints = {arm: arms[arm]["endpoint"] for arm in ARMS}
    if endpoints != grid["endpoints"]:
        return None
    for arm in ARMS:
        rounds = arms[arm]["rounds"]
        if not rounds or rounds[-1]["endpoint"] != endpoints[arm]:
            return None
    region = dict(center=path["region_center"], width_km=path["box_width_km"])
    return region_key(region), endpoints


def published_paths(original_root, extras):
    endpoints = {}
    regional = MEASUREMENTS.parent.parent / "regional-release/predictions.json"
    original = json.loads(regional.read_bytes())["rows"]
    cases = [(original_root, item["run_id"]) for item in original] + list(extras)
    for root, run in cases:
        store = FastStandardAnalysisStore(root)
        match = path_evidence(store.position_path(run), store.position_grid(run))
        if match is not None:
            key, xy = match
            endpoints[key] = dict(source=run, endpoints=xy)

    edge = json.loads(gzip.decompress((MEASUREMENTS / "edge-solvers.json.gz").read_bytes()))
    mirrors = json.loads(gzip.decompress((MEASUREMENTS / "region-mirrors.json.gz").read_bytes()))
    saved = {**{name: edge[name] for name in ("north-solver.json", "south-solver.json")},
             "north_stock_position": mirrors["north_stock_position"]}
    for name, row in saved.items():
        packet = row["evidence"]
        match = path_evidence(packet["position_path"], packet["position_grid"])
        if match is not None:
            key, xy = match
            endpoints[key] = dict(source=name, endpoints=xy)
    return endpoints


def rescore(native, archive, track_config, saved):
    raw = Path(native).read_bytes()
    if sha256(raw).hexdigest() != saved["native_sha256"].removeprefix("sha256:"):
        raise ValueError("Detector input differs from the saved all-track scores")
    start = process_time()
    settings = TrackConfig(**json.loads(Path(track_config).read_bytes())["config"])
    tracks = prepare_tracks(json.loads(raw), settings)
    # The compact solver passes the in-memory JSON representation of the tracks.
    tracks = json.loads(json.dumps(tracks, default=_json_value, allow_nan=False))
    graph_cpu_s = process_time() - start
    center, width = region_key(saved["offer"])
    start = process_time()
    result = causal_probes(tracks, TleArchiveReader(Path(archive)), SearchRegion(center, width))
    score_cpu_s = process_time() - start
    result = json.loads(json.dumps(result, allow_nan=False))
    scientific_keys = set(result)
    if any(result[key] != saved[key] for key in scientific_keys):
        changed = sorted(key for key in scientific_keys if result[key] != saved[key])
        raise ValueError(f"Causal replay differs from saved inputs: {changed}")
    return result["points"], dict(exact_probe_match=True, graph_cpu_s=graph_cpu_s,
                                  catalogue_and_probes_cpu_s=score_cpu_s)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_publications", type=Path)
    parser.add_argument("--extra-publication", nargs=2, action="append", default=[],
                        metavar=("ROOT", "RUN"))
    parser.add_argument("--rescore", nargs=4, action="append", default=[],
                        metavar=("SAVED_OFFER", "DETECTIONS", "ARCHIVE", "TRACK_CONFIG"))
    args = parser.parse_args()
    saved = saved_offers()
    endpoints = published_paths(args.original_publications, args.extra_publication)
    replay = {name: pins for name, *pins in args.rescore}
    if replay.keys() - saved.keys():
        raise ValueError("Unknown saved offer")
    outcomes = {}
    for name, offer in saved.items():
        key = region_key(offer["offer"])
        fit = endpoints.get(key, dict(source=None, endpoints={}))
        receipt = {}

        def score():
            if name not in replay:
                return offer["points"]
            points, metrics = rescore(*replay[name], offer)
            receipt.update(metrics)
            return points

        gated = inspect_boundary(fit["endpoints"], key[1], score)
        if gated.get("diagnostic_error"):
            raise ValueError(gated["diagnostic_error"])
        outcomes[name] = dict(fit, **gated, rescore=receipt or None)
    print(json.dumps(outcomes, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
