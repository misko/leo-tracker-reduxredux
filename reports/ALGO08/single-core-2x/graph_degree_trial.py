"""Compare complete Graph preparations in reversed pairs on two pinned saved inputs."""

import argparse
import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from leo.analysis import polynomial_tracklets as poly
from leo.analysis.localization_v3.tracks import prepare_tracks
from tools.pipeline_eval.variants.experimental.graph_degree_bound import best_piece
from tools.pipeline_eval.variants.experimental.graph_path import native_paths

from .graph_saved_trial import digest

INPUTS = {
    "DS30-0008": ("restored-graph-profile-0008/native.json",
                  "6bbbe162cdaf60befe353463afd155970df08d4b9d98366fe5a1f109c48c6746"),
    "Southern portable": ("portable-v5-geodiverse/0ea3bb46005a423fcdf0239e/native.json",
                          "17dbb334d49e37ad439b4170aed3174ba485059e04ef6121ce8968c4f72f77e9"),
}


def check(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Unexpected input {path}")
    return data


def run(bench, config):
    check(Path(poly.__file__), "933b83ce5e414a8441c62d17f8e5eb75e07b79cada283bf681193f7316346922")
    library = bench / "integration-restored-scout-graph/graph-path.so"
    check(library, "e623daaff9ac9fddc709d26af2a1fecd696aa133568c3d6c0a4d10e6b481d627")
    cfg = poly.TrackConfig(**json.loads(check(
        config, "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"))["config"])
    result = {}
    for case, (path, expected) in INPUTS.items():
        native = json.loads(check(bench / path, expected))
        rows = []
        for mode in ("original", "bounded", "bounded", "original"):
            select = poly._best_piece if mode == "original" else best_piece
            with native_paths(library, required=True), patch.object(poly, "_best_piece", select):
                start, wall = process_time(), perf_counter()
                prepared = prepare_tracks(native, cfg)
                cpu, elapsed = process_time() - start, perf_counter() - wall
            rows.append(dict(mode=mode, cpu_s=cpu, elapsed_s=elapsed,
                             prepared_sha256=digest(prepared)))
        if len({r["prepared_sha256"] for r in rows}) != 1:
            raise ValueError(f"Changed Graph evidence on {case}")
        result[case] = dict(native_sha256=expected, runs=rows, tracks=len(prepared["tracks"]),
                            curved=len(prepared["curved_indices"]),
                            assigned=prepared["graph_points"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("bench", "config", "output"):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    receipt = run(args.bench, args.config)
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
