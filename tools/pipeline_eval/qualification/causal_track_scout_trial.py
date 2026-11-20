"""Lock prospective per-probe center proposals before opening score references."""

import argparse
import gzip
import json
import os
from collections import Counter
from hashlib import sha256
from itertools import groupby
from pathlib import Path
from time import perf_counter, process_time_ns

from ..__main__ import encoded, save_json
from ..variants import causal_track_scout, coherent_peak_filter, track_epoch
from .factor_cross import winner
from .input_factor_bridge import REPO, SCREEN, _sha, check, read
from .peak_support import lane
from .peak_support_trial import BAND, ORDER

REPORT = SCREEN / "receiver-core/causal-track-scout"


def source_plan():
    parent = BAND / "prediction-lock.json"
    pin = read(parent)
    if set(pin["cases"]) != set(ORDER):
        raise ValueError("wide input roster differs from the declared six")
    sources = (
        Path(__file__),
        Path(causal_track_scout.__file__),
        Path(coherent_peak_filter.__file__),
        Path(track_epoch.__file__),
        Path(__file__).with_name("factor_cross.py"),
        Path(__file__).with_name("peak_support.py"),
        REPORT / "PROTOCOL.md",
        parent,
    )
    return dict(
        cases=list(ORDER),
        development=list(ORDER[:2]),
        reserves=list(ORDER[2:]),
        sources={str(path.relative_to(REPO)): _sha(path) for path in sources},
        wide={ident: pin["files"][f"native/{ident}.json.gz"] for ident in ORDER},
        cpus=sorted(os.sched_getaffinity(0)),
        max_centers=causal_track_scout.MAX_CENTERS,
        max_tracklets_per_lane=causal_track_scout.MAX_TRACKLETS,
    )


def prospective(ident, document, publish):
    """Emit both receivers' rows, then read either current candidate list."""
    started = perf_counter()
    source = document["source"]
    scout = causal_track_scout.TrackScout(source["sample_rate_hz"])
    center_counts = Counter()
    clock = dict(propose_ns=0, update_ns=0)
    peak_tracks = 0
    previous = -1
    for visit, grouped in groupby(source["probes"], key=lambda r: r["visit_index"]):
        stereo = list(grouped)
        if visit <= previous or [r["receiver_id"] for r in stereo] != [0, 1]:
            raise ValueError("native timeline is not a sequence of complete ordered stereo visits")
        previous = visit
        keys = [(lane(p), p["valid_start_counter"]) for p in stereo]
        for p, (key, counter) in zip(stereo, keys, strict=True):
            begin = process_time_ns()
            predicted = scout.propose(key, counter)
            clock["propose_ns"] += process_time_ns() - begin
            center_counts[len(predicted)] += 1
            publish(
                dict(
                    case=ident,
                    visit=visit,
                    counter=counter,
                    receiver_id=p["receiver_id"],
                    channel=p["channel"],
                    centers=[center for center, _ in predicted],
                    epochs=[epoch for _, epoch in predicted],
                )
            )
        for p, (key, counter) in zip(stereo, keys, strict=True):
            begin = process_time_ns()
            index = winner(p["candidates"])
            point = (
                None
                if index is None
                else coherent_peak_filter.Peak.from_candidate(p, counter, p["candidates"][index])
            )
            scout.observe(key, counter, point)
            clock["update_ns"] += process_time_ns() - begin
            peak_tracks = max(peak_tracks, len(scout.tracks[key]))
    return dict(
        probe_rows=sum(center_counts.values()),
        capture_exclusions=len(document["provenance"]["excluded_windows"]),
        center_counts=dict(center_counts),
        max_live_tracklets_per_lane=peak_tracks,
        lanes=len(scout.tracks),
        propose_cpu_s=clock["propose_ns"] * 1e-9,
        update_cpu_s=clock["update_ns"] * 1e-9,
        complete_proposal_wall_s=perf_counter() - started,
    )


def run():
    authority = REPORT / "source-lock.json"
    if authority.exists():
        raise ValueError("causal track-scout source was already sealed")
    pins = source_plan()
    save_json(authority, pins)
    timing = {}
    out = REPORT / "proposals.jsonl.gz"
    with (
        out.open("xb") as buffer,
        gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0, compresslevel=4) as stream,
    ):
        for ident in pins["cases"]:
            raw = BAND / "native" / f"{ident}.json.gz"
            check(raw, pins["wide"][ident])
            content = gzip.decompress(raw.read_bytes())
            document = json.loads(content)
            timing[ident] = prospective(
                ident, document, lambda row: stream.write(encoded(row) + b"\n")
            )
            timing[ident]["wide_native_sha256"] = sha256(content).hexdigest()
            print(ident, timing[ident]["center_counts"], flush=True)
    for path, digest in pins["sources"].items():
        check(REPO / path, digest)
    save_json(REPORT / "timing.json", timing)
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=pins["cases"],
            source_lock_sha256=_sha(authority),
            files={n: _sha(REPORT / n) for n in ("timing.json", out.name)},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    run()
