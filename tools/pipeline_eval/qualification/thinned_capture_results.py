"""Score the frozen thinned-capture held panel and preserve diagnostic failures."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path
from statistics import median, quantiles

import numpy as np

from ..__main__ import encoded, save_json
from . import thinned_capture_eval as run


def load(case):
    return json.loads(gzip.decompress((run.REPORT / f"{case}.json.gz").read_bytes()))


def positives(rows):
    counters = Counter()
    for rec in rows:
        counters.update(
            original=rec["production_positive"],
            new=rec["native_positive"],
            matched=len(rec["positive_matches"]),
            missing=rec["production_only"],
            surplus=rec["native_only"],
        )
    return dict(counters)


def primary_acquisitions(calls):
    first = {}
    for call in calls:
        first.setdefault(call["rx"], call)
    return first


def measured_basins(rows):
    result = Counter()
    for row in rows:
        roles = row["pairs"][0]["modes"]
        source = primary_acquisitions(roles["capture"]["acquisitions"])
        thinned = primary_acquisitions(roles["thinned"]["acquisitions"])
        for a, b in zip(source.values(), thinned.values(), strict=True):
            if a["rx"] != b["rx"] or a["anchors"] != b["anchors"]:
                raise ValueError("the original first acquisition geometry changed")
            original = {tuple(q) for q in a["peaks"] if a["peaks"]}
            selected = {tuple(q) for q in b["peaks"] if b["peaks"]}
            covered = sum(
                any(lo <= epoch < hi for lo, hi in b["eligible_ranges"]) for epoch, _ in original
            )
            result.update(
                original=len(original),
                chosen=len(selected),
                retained=len(original & selected),
                original_in_scored_interior=covered,
            )
    return dict(result)


def wide_case(case, folder):
    """Read the published wide detector shortlist, independently of its saved timing run."""
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    d = load(case)
    frozen = run._load_case(case)
    _, _, provenance = run.lineage.source_lineage(frozen)
    if provenance != d["provenance"]:
        raise ValueError("installed wide diagnostic context changed")
    edge = "lower" if case.startswith("DS26") else "upper"
    template = tuple(
        np.asarray(qin_edge_pilot_frame(10_000_000, edge, symbol_roll=roll), dtype="<c16")
        for roll in (0, CONTROL_SYMBOL_ROLL)
    )
    result = {}
    with NativeShortWindow(
        str(run.WIDE), *template, sample_rate_hz=10_000_000, fractional_epoch=True
    ) as detector:
        for row in (r for r in d["rows"] if r["status"] == "processed"):
            locator = frozen["recording"]["segments"][row["segment"]]
            source = dict(
                recording_path=str(run.BULK / locator["path"]),
                recording_sha256="sha256:" + locator["sha256"],
            )
            (window,) = run.load_windows(source, (row["sequence"],))
            if window.iq_sha256 != row["iq_sha256"]:
                raise ValueError("wide shortlist diagnostic used different raw IQ")
            native = detector.analyze(window.samples)
            probes = [
                run._probe(
                    window,
                    rx["receiver_id"],
                    (run._from_native(i, c) for i, c in enumerate(rx["candidates"])),
                )
                for rx in native["rows"]
            ]
            if encoded(probes) != encoded(row["pairs"][0]["modes"]["wide"]["probes"]):
                raise ValueError("wide shortlisted diagnostic does not reproduce timed output")
            result[str(row["visit"])] = {
                rx["receiver_id"]: [
                    [c["coarse_epoch"], c["coarse_cfo_hz"]] for c in rx["candidates"]
                ]
                for rx in native["rows"]
            }
    save_json(folder / f"{case}-wide-shortlists.json", result)


def package(folder):
    docs = {c: load(c) for c in run.CASES}
    rows = [r for d in docs.values() for r in d["rows"] if r["status"] == "processed"]
    pairs = [p for r in rows for p in r["pairs"]]
    stat, stage = {}, {}
    for mode in run.MODES:
        entries = [p["modes"][mode] for p in pairs]
        wall = [e["wall_ms"] for e in entries]
        cpu = [e["cpu_ms"] for e in entries]
        stat[mode] = dict(
            calls=len(entries),
            median_wall_ms=median(wall),
            p90_wall_ms=quantiles(wall, n=10)[8],
            median_cpu_ms=median(cpu),
            median_cpu_le_20_ms=median(cpu) <= 20,
            wall_at_most_20_ms=sum(x <= 20 for x in wall),
        )
        stage[mode] = Counter()
        for entry in entries:
            clocks = entry["stage_cpu_ms"]
            if mode == "wide":
                for row in clocks:
                    stage[mode].update(row)
            else:
                stage[mode].update(clocks)
    invocations = [a for p in pairs for a in p["modes"]["thinned"]["acquisitions"]]
    wide_diag = {
        case: json.loads((folder / f"{case}-wide-shortlists.json").read_bytes())
        for case in run.CASES
    }
    wide_basins = Counter()
    for case, doc in docs.items():
        for row in (r for r in doc["rows"] if r["status"] == "processed"):
            expected = primary_acquisitions(row["pairs"][0]["modes"]["capture"]["acquisitions"])
            actual = wide_diag[case][str(row["visit"])]
            for rx, command in expected.items():
                a, b = (set(map(tuple, v)) for v in (command["peaks"], actual[str(rx)]))
                wide_basins.update(original=len(a), chosen=len(b), retained=len(a & b))
    cases = {
        case: dict(
            admitted=sum(r["status"] == "processed" for r in data["rows"]),
            excluded=sum(r["status"] != "processed" for r in data["rows"]),
            harness_peak_rss_kib=data["peak_rss_kib"],
            controls={
                k: {m: positives(x["positives"][m]) for m in ("thinned", "wide")}
                for k, x in data["controls"].items()
            },
        )
        for case, data in docs.items()
    }
    summary = dict(
        timing=stat,
        stage_cpu_sums_ms={k: dict(v) for k, v in stage.items()},
        held_positives={
            m: positives([q for row in rows for q in row["positives"][m]])
            for m in ("thinned", "wide")
        },
        held_basin_keys=measured_basins(rows),
        wide_surviving_basin_keys=dict(wide_basins),
        rescored=dict(
            calls=len(invocations),
            original_cells=sum(a["original_cells"] for a in invocations),
            rescored_cells=sum(a["rescored_cells"] for a in invocations),
            median_rescored_cells=median(a["rescored_cells"] for a in invocations),
            bit_exact_to_original_full_calls_cells=sum(
                p["bit_exact_rescored_cells"] for p in pairs
            ),
            maximum_explicit_numpy_peak_bytes=max(
                a["coarse_numpy_buffer_peak_bytes"] for a in invocations
            ),
            thin_cpu_sum_ms={
                k: sum(a[k] for a in invocations)
                for k in ("proposal_cpu_ms", "nomination_cpu_ms", "rescore_cpu_ms")
            },
        ),
        cases=cases,
    )
    save_json(run.REPORT / "qualification.json", summary)
    save_json(run.REPORT / "wide-shortlists.json", wide_diag)
    names = (
        "PROTOCOL.md",
        "source-lock.json",
        "qualification.json",
        "wide-shortlists.json",
        *(f"{c}.json.gz" for c in run.CASES),
    )
    save_json(
        run.REPORT / "evidence-lock.json",
        dict(
            cases=list(run.CASES),
            files={n: run._sha(run.REPORT / n) for n in names},
            scorer_sha256=run._sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--wide-case", choices=run.CASES)
    args = parser.parse_args()
    if args.wide_case:
        wide_case(args.wide_case, args.work)
    else:
        package(args.work)
