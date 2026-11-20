"""Capture the measured Graph output without changing the receiver's numerical state."""

import argparse
import json
import sys
from pathlib import Path


def trace(prepared, path):
    exported = {
        "points": prepared["graph_points"],
        "positive": len(prepared["observations"]),
        "curved": len(prepared["curved_indices"]),
        "tracks": [
            {
                "receiver": int(track["receiver"]),
                "channel": int(track["channel"]),
                "ids": track["observation_ids"],
                "times_s": track["times"].tolist(),
                "graph_cfo_hz": track["values"].tolist(),
            }
            for track in prepared["tracks"]
        ],
    }
    path.write_text(json.dumps(exported, allow_nan=False))


def observe_graph(path):
    from leo.application import localization_v3

    original = localization_v3.prepare_tracks

    def wrapped(document, config):
        prepared = original(document, config)
        trace(prepared, path)
        return prepared

    localization_v3.prepare_tracks = wrapped


def standalone(bundle, native, config, out):
    sys.path.insert(0, str(bundle))
    from leo.analysis.localization_v3.tracks import prepare_tracks

    from leo.analysis.polynomial_tracklets import TrackConfig

    configuration = TrackConfig(**json.loads(config.read_bytes())["config"])
    trace(prepare_tracks(json.loads(native.read_bytes()), configuration), out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("bundle", "native", "config", "out"):
        parser.add_argument(field, type=Path)
    standalone(**vars(parser.parse_args()))
