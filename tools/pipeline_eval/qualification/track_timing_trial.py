"""Test a causal pilot timing forecast conditional on measured Doppler track membership."""

import argparse
import gzip
import json
from collections import defaultdict
from hashlib import sha256
from math import isclose, isfinite
from pathlib import Path
from time import perf_counter, process_time

from ..__main__ import ROOT, local_output, save_json
from ..scoring import distribution
from ..variants.coherent_peak_filter import FOLD_HZ, FRAME_RATE_HZ, Peak, wrapped
from ..variants.track_epoch import predict
from .alias_attribution import observation_id
from .factor_cross import winner
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file

PARENT = ROOT / "reports/2026_11_19_receiver_screening/receiver-core"
DEFAULT_OUT = PARENT / "track-timing"
ARCHIVE = PARENT / "alias-attribution"
CASES = ("DS26-0036", "DS29-0082", "DS26-0237", "DS29-0174")
SOURCES = ("capture-era", "wide")


def authenticated_inputs(folder):
    lock = json.loads((folder / "prediction-lock.json").read_bytes())
    for name in ("plan.json", "graph-traces.jsonl.gz"):
        if _sha(folder / name) != lock["files"][name]:
            raise ValueError(f"changed Graph input: {name}")
    authorities = json.loads((folder / "plan.json").read_bytes())["authorities"]
    graphs = {}
    with gzip.open(folder / "graph-traces.jsonl.gz", "rt") as stream:
        for row in map(json.loads, stream):
            key = row["id"], "capture-era"
            if row["method"] == "wide-graph" and row["id"].endswith("-stock"):
                key = row["id"].removesuffix("-stock"), "wide"
            elif row["method"] != "capture-era-graph":
                continue
            if key in graphs or row["status"] != "ok":
                raise ValueError("Graph lacks a unique complete input")
            graphs[key] = row["graph"]
    if set(graphs) != {(ident, source) for ident in CASES for source in SOURCES}:
        raise ValueError("complete capture-era and wide Graph tracks are required for four cases")
    return authorities, graphs


def measured_peaks(document):
    source = document["source"]
    session, rate = source["session_id"], source["sample_rate_hz"]
    anchor = document["clock_anchor"]["sample_counter"]
    # The original Graph numbers the sorted native receiver IDs starting at one.
    receiver_numbers = {
        key: index
        for index, key in enumerate(sorted({p["receiver_id"] for p in source["probes"]}), 1)
    }
    found = {}
    for probe in source["probes"]:
        index = winner(probe["candidates"])
        if index is None:
            continue
        key = observation_id(session, probe)
        if key in found:
            raise ValueError("duplicate winning-probe sample identity")
        best = probe["candidates"][index]
        peak = Peak.from_candidate(probe, probe["valid_start_counter"], best)
        t = (peak.counter - anchor) / rate + source["probe_ms"] / 2000
        lane = (
            receiver_numbers[probe["receiver_id"]],
            int(probe["channel"]),
            probe["actual_rf_hz"],
            probe["edge"],
        )
        if not all(map(isfinite, (peak.epoch, peak.cfo_hz, t, lane[2]))):
            raise ValueError("nonfinite native winner")
        found[key] = (peak, t, lane)
    return found, anchor, rate


def opportunities(document, graph):
    peaks, anchor, rate = measured_peaks(document)
    owned, triples = set(), []
    triple_count = 0
    for track_index, track in enumerate(graph["tracks"]):
        points, lanes = [], []
        for key, t, hz in zip(track["ids"], track["times_s"], track["graph_cfo_hz"], strict=True):
            point, measured_time, lane = peaks[key]
            if (
                key in owned
                or lane[:2] != (track["receiver"], track["channel"])
                or not isclose(t, measured_time, abs_tol=1e-8, rel_tol=0)
                or abs(wrapped(hz - point.cfo_hz, FOLD_HZ)) > 1e-5
            ):
                raise ValueError("Graph ownership, clock, lane or lifted CFO differs from native")
            owned.add(key)
            points.append(Peak(point.visit, point.counter, point.epoch, hz))
            lanes.append(lane)
        for k, target in enumerate(points[2:], 2):
            triple_count += 1
            if lanes[k - 2] != lanes[k - 1] or lanes[k - 1] != lanes[k]:
                continue
            receiver, channel, rf, edge = lanes[k]
            forecast = predict(points[k - 2], points[k - 1], target.counter, rate, rf)
            if forecast is None:
                continue
            triples.append(
                dict(
                    target=track["ids"][k],
                    track=track_index,
                    receiver=receiver,
                    channel=channel,
                    rf=rf,
                    edge=edge,
                    block=(target.counter - anchor) // (30 * rate),
                    counter=target.counter,
                    observed_samples=target.epoch,
                    linear_samples=forecast.linear_samples,
                    doppler_samples=forecast.doppler_samples,
                    first_rate_ppm=forecast.first_rate_ppm,
                )
            )
    return triples, dict(
        positive_probes=len(peaks),
        graph_tracks=len(graph["tracks"]),
        graph_owned=len(owned),
        candidate_triples=triple_count,
        eligible_triples=len(triples),
    )


def score(triples, rate):
    period = rate / FRAME_RATE_HZ
    lanes = defaultdict(list)
    for row in triples:
        key = tuple(row[k] for k in ("receiver", "channel", "rf", "edge", "block"))
        lanes[key].append(row)
    for members in lanes.values():
        ordered = sorted(members, key=lambda r: r["counter"])
        for i, row in enumerate(ordered):
            row["history_pass"] = abs(row["first_rate_ppm"]) <= 50
            shifted = ordered[(i + len(ordered) // 2) % len(ordered)]
            row["null_target"] = shifted["target"] if len(ordered) > 1 else None
            for name in ("linear", "doppler"):
                row[name + "_error"] = abs(
                    wrapped(row[name + "_samples"] - row["observed_samples"], period)
                )
            row["shuffle_error"] = (
                abs(wrapped(row["doppler_samples"] - shifted["observed_samples"], period))
                if row["null_target"]
                else None
            )
    return triples


def summarize(rows):
    passing = [row for row in rows if row["history_pass"]]
    common = [row for row in passing if row["shuffle_error"] is not None]
    stats = dict(history_pass=len(passing), comparable=len(common))
    for name in ("linear", "doppler", "shuffle"):
        errors = [row[name + "_error"] for row in common]
        stats[name + "_median_samples"] = distribution(errors)["p50"]
        for tolerance in (1, 2, 20):
            stats[f"{name}_within_{tolerance}"] = sum(error <= tolerance for error in errors)
    stats["admission_criterion"] = bool(
        rows
        and common
        and 4 * len(passing) >= len(rows)
        and 2 * stats["doppler_within_2"] >= len(common)
        and 10 * (stats["doppler_within_2"] - stats["shuffle_within_2"]) >= len(common)
    )
    return stats


def run(out, archive=ARCHIVE):
    if (out / "prediction-lock.json").exists():
        raise FileExistsError(f"predictions already sealed in {out}; choose a new output directory")
    authorities, graphs = authenticated_inputs(archive)
    from ..variants import track_epoch

    sources = [
        Path(__file__),
        Path(track_epoch.__file__),
        out / "PROTOCOL.md",
        archive / "prediction-lock.json",
    ]
    source_lock = dict(
        files={
            str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else p.name: _sha(p) for p in sources
        },
        native_sources={
            case: {s: authorities[case]["native_sha"][s] for s in SOURCES} for case in CASES
        },
    )
    lock_path = out / "source-lock.json"
    if lock_path.exists() and json.loads(lock_path.read_bytes()) != source_lock:
        raise ValueError("source or input differs from the frozen track timing study")
    save_json(lock_path, source_lock)
    all_rows, comparisons = [], []
    for case in CASES:
        for source in SOURCES:
            wall, cpu = perf_counter(), process_time()
            record = authorities[case]
            path = Path(record["paths"][source])
            if source == "wide":
                # The public evidence is portable across checkouts.
                path = PARENT.parent / "detector-origins/whole-band/native" / f"{case}.json.gz"
            with gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb") as f:
                raw = f.read()
            if sha256(raw).hexdigest() != record["native_sha"][source]:
                raise ValueError(f"changed {source} winner input for {case}")
            doc = json.loads(raw)
            opportunities_, counts = opportunities(doc, graphs[(case, source)])
            rows = score(opportunities_, doc["source"]["sample_rate_hz"])
            all_rows.extend(dict(id=case, source=source, **r) for r in rows)
            comparisons.append(
                dict(
                    id=case,
                    source=source,
                    cohort="diagnostic" if case in CASES[:2] else "confirmation",
                    **counts,
                    **summarize(rows),
                    cpu_s=process_time() - cpu,
                    wall_s=perf_counter() - wall,
                )
            )
    pack(out / "targets.jsonl.gz", all_rows)
    csv_file(out / "track-timing.csv", comparisons)
    names = ("source-lock.json", "track-timing.csv", "targets.jsonl.gz")
    save_json(out / "prediction-lock.json", {"files": {n: _sha(out / n) for n in names}})
    return comparisons


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=DEFAULT_OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.out), indent=2))
