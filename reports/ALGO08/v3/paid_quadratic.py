"""Evaluate the registered sparse quadratic graph on identical paid packets."""

import argparse
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from aperture_trial import read, write
from paid_graph_trial import run
from sparse_consensus_trial import CASES


def quadratic(config):
    return replace(config, max_degree=2, points_per_coefficient=2, min_points=6)


class GraphOnly(Exception):
    pass


def measure(case, original, output, graph_only):
    baseline = read(original)
    if baseline["identity"]["case"] != case or baseline["identity"]["mode"] != "margin":
        raise ValueError("Expected the matched maximum-margin case")
    def observe(native, identity, config):
        from leo.analysis.localization_v3.tracks import prepare_tracks
        from tools import algo08_position

        if identity["native_sha256"] != baseline["identity"]["native_sha256"]:
            raise ValueError("Sparse packet changed")
        identity["mode"] = "quadratic"
        identity["graph_parameters"] = {"max_degree": 2, "points_per_coefficient": 2, "min_points": 6}
        if graph_only:
            prepared = prepare_tracks(native, quadratic(config))
            write(output, dict(identity=identity, observations=len(prepared["observations"]),
                               arcs=len(prepared["tracks"]), graph_points=prepared["graph_points"],
                               curved=len(prepared["curved_indices"]), status=prepared["status"]))
            raise GraphOnly()
        factory = algo08_position.TrackConfig
        stack.enter_context(patch.object(algo08_position, "TrackConfig", lambda **cfg: quadratic(factory(**cfg))))

    try:
        with ExitStack() as stack:
            run(case, "margin", output, observe=observe)
    except GraphOnly:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("original", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--graph-only", action="store_true")
    parser.add_argument("--eligibility", type=Path)
    args = parser.parse_args()
    if not args.graph_only:
        eligibility = read(args.eligibility)
        if eligibility["curved"] < 1 or eligibility["identity"]["case"] != "south-containing":
            raise ValueError("Southern sparse graph did not pass preregistered stage")
    measure(args.case, args.original, args.output, args.graph_only)
