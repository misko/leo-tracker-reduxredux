"""Count projected time support for the exact stopped proof prefixes."""

import argparse
import gzip
from hashlib import sha256
import json
from math import isclose, log, pi, sqrt
from pathlib import Path


HERE = Path(__file__).resolve().parent
PHYSICAL = {
    "dense": ("0008", "9d59d59b3ace42f93b50e7ab29e2b2fd7856e247e01d64c353bce3e395705d9a"),
    "medium": ("0057", "473c53d29027be9246070d056367903815321db33dd24b944e93672fa751f561"),
}
RECEIPT_SHA = "2a9da8107bf494e6c6d3155ff8c790fb8f236b9cb1d3970b822361ba2b33e1c7"
TRACKS_SHA = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
GRAPH_SHA = "e623daaff9ac9fddc709d26af2a1fecd696aa133568c3d6c0a4d10e6b481d627"


def cell_bound(all_support, receiver_support, prefixes, orbits):
    """Count a full orbit at each retained time, including all cap endpoints."""
    if not receiver_support or not all_support or orbits < 1:
        raise ValueError("A supported geometry requires tracks and projected orbits")
    endpoints = {x for t in receiver_support for x in (t[0], t[-1])}
    ordered = sorted(receiver_support, key=lambda t: -len(t))
    totals = {x for t in all_support for x in t}
    receiver = {x for t in receiver_support for x in t}
    counts = []
    for k in prefixes:
        if not 0 <= k <= len(ordered):
            raise ValueError("The paid prefix lies outside the scored receiver's tracks")
        counts.append(len(endpoints | {x for t in ordered[:k] for x in t}))
    geometry = orbits * len(totals) * (len(prefixes)+1)
    receiver_only = orbits * len(receiver) * (len(prefixes)+1)
    lazy = orbits * (len(receiver)+sum(counts))
    return dict(all_unique_times=len(totals), receiver_unique_times=len(receiver),
                required_endpoint_times=len(endpoints), exterior_unique_times=counts,
                projected_orbits=orbits, all_cells=geometry, receiver_only_cells=receiver_only,
                lazy_cells=lazy, avoided_cells=geometry-lazy, prefix_only_avoided_cells=receiver_only-lazy)


def checked(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Saved witness or released source changed at {path}")
    return data


def track_support(packet, case):
    if case in PHYSICAL:
        suffix, pin = PHYSICAL[case]
        path = Path(f"/dev/shm/leo-conflict-components-{suffix}-result04/result.json")
        witness = json.loads(checked(path, pin))
        return witness["tracks"], dict(original_trace_sha256=pin)
    from aperture_trial import RELEASE, PAYLOAD
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from tools.pipeline_eval.variants.experimental.graph_path import native_paths

    config = json.loads(checked(RELEASE/"assets/tracks.json", TRACKS_SHA))["config"]
    path = PAYLOAD/"graph-path.so"
    checked(path, GRAPH_SHA)
    with native_paths(path, required=True) as counts:
        tracks = prepare_tracks(packet, TrackConfig(**config))["tracks"]
    return tracks, dict(released_track_asset_sha256=TRACKS_SHA, graph_path_sha256=GRAPH_SHA,
                        native_graph_counts=dict(counts), numerical_score_calls=0)


def inspect(case, stage):
    source = stage["source"]
    packet = json.loads(checked(Path(source["packet"]), source["native_sha256"]))
    tracks, provenance = track_support(packet, case)
    original = packet["source"]
    times = {}
    for row in original["probes"]:
        counter = row["valid_start_counter"]
        identity = f"{original['session_id']}:{row['receiver_id']}:{counter}"
        times["sha256:"+sha256(identity.encode()).hexdigest()] = counter
    support = [(t["receiver"], [times[i] for i in t["observation_ids"]]) for t in tracks]
    selected = [s for receiver, s in support if receiver == 1]
    all_support = [s for _, s in support]
    meta, bounded = stage["meta"], stage["bounded"]
    if (len(support) != meta["track_count"] or len(selected) != stage["audited_receiver_tracks"]
            or sum(map(len, all_support)) != meta["graph_points"]):
        raise ValueError("The archived original track support changed")
    catalogue = meta["catalogue_orbits"]
    for row in bounded["exteriors"]:
        for track, k, cap in zip(selected, row["possible_orbits"], row["cap"], strict=True):
            n = len(track)
            peak = (n-1)*log((1/4.4e-6)/(sqrt(2*pi)*150))-.5*log(n)
            expected = max(0., peak-.69*((catalogue//k).bit_length()-1))+1. if k else 0.
            if not isclose(cap, expected, abs_tol=1e-11, rel_tol=1e-12):
                raise ValueError("The observed caps and archived track ordering disagree")
    result = cell_bound(all_support, selected, [r["evaluated"] for r in bounded["exteriors"]],
                        meta["potentially_visible_orbits"])
    if result["all_cells"] != bounded["native"]["cells"]:
        raise ValueError("The actual projected cell inventory changed")
    return result | dict(provenance=provenance, detector_sha256=source["native_sha256"],
                         excludes_released_fallback=bounded["released"] is not None)


def run(output):
    from dense_geographic_trial import host

    archive = HERE/"measurements/regional-decision-bound.json.gz"
    data = gzip.decompress(archive.read_bytes())
    if sha256(data).hexdigest() != RECEIPT_SHA:
        raise ValueError("Measured prefix archive differs")
    report = {case: inspect(case, stage) for case, stage in json.loads(data)["replays"].items()}
    with output.open("x") as stream:
        json.dump(dict(source_sha256=RECEIPT_SHA, cases=report, machine=host(), waveform_reads=0,
                       regional_score_calls=0, retimed=False), stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
