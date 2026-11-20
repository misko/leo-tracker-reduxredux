"""Authenticate and overlay four complete receiver outputs on the original roof panel."""

import argparse
from bisect import bisect_right
from collections import Counter
from itertools import combinations, pairwise
from pathlib import Path

from .. import corpus
from ..__main__ import local_output, read_predictions, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds, validate_result
from . import anchor_receiver_full as anchored
from . import anchor_receiver_full_results as anchor_scores
from . import full_receiver_comparison as prior
from . import phase_support_results as phase_scores
from . import phase_support_trial as phase
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

REPORT = prior.SCREEN / "refinement/full-receivers"
CHART = "full-receiver-refinement-roof135"
METHOD = "full_receiver_refinement"
ADAPTIVE = "phase_support_causal"
SERIES = (
    (prior.COMPACT, "Compact v5 secant", "one"),
    (prior.CLOCK, "Native smooth clock", "all_visits"),
    (anchored.METHOD, "Native curve anchors", "one_native_factors"),
    (ADAPTIVE, "Native adaptive phase", "stock"),
)
MATCH = ("native_sha256", "catalog_sha256", "tile")
FULL_MATCH = ("input_sha256", *MATCH, "observation_sha256")
POSITIONS = "positions.jsonl.gz"
FILES = (POSITIONS, "sources.json", "summary.json", "scores.csv", "crossings.json")


def verify_native(ident, row, control, method, stage):
    prior.require_fields(
        row,
        dict(
            {key: control[key] for key in FULL_MATCH},
            id=ident,
            recording=ident,
            method=method,
            address_space_limit_mib=512,
        ),
    )
    validate_result(row["result"])
    if (
        row["result"]["status"] not in ("ok", "withheld")
        or set(row["result"]["arms"]) != set(ARMS)
        or not {"archive_and_peak_selection", "graph", stage} <= row["stages"].keys()
        or not 0 < row["proc_memory_kib"]["VmPeak"] <= 512 * 1024
    ):
        raise ValueError(f"{ident} does not attest to a complete capped native receiver")


def anchor_predictions(inputs, joint):
    folder = anchored.REPORT
    lock = prior.seal(folder, "prediction-lock.json", (POSITIONS, "plan.json"))
    plan = prior.read(folder / "plan.json")
    prior.require_fields(plan, dict(source=anchored.sources(anchored.old.base.BUNDLE)))
    stock_plan = prior.read(anchored.STOCK / "plan.json")
    if plan["cases"] != stock_plan["cases"]:
        raise ValueError("anchor roof and omitted requests differ from the native control plan")
    records = read_predictions(folder / POSITIONS)
    prior.roster_matches(lock["cases"], records, "anchor seal")
    prior.roster_matches([job["id"] for job in plan["cases"]], records, "anchor plan")
    anchor_scores.matched_stock(records, plan)
    run = lock["run"]
    if (
        run["attempted"] != len(records)
        or run["scheduled"] != len(records)
        or run["statuses"] != Counter(r["result"]["status"] for r in records.values())
        or not 0 < run["wall_s"] <= plan["wall_cap_s"]
    ):
        raise ValueError("anchor replay does not reconcile with its execution receipt")
    roof = {ident: row for ident, row in records.items() if row["cohort"] == "roof"}
    prior.roster_matches(roof, inputs, "anchor roof")
    for ident, row in roof.items():
        verify_native(ident, row, joint[ident], anchored.METHOD, "anchor_backend")
    return roof, prior.ledger_entry(folder, POSITIONS, "prediction-lock.json", lock)


def phase_predictions(inputs, joint):
    folder = phase.REPORT
    plan, records, _, missing = phase_scores.authority(folder)
    stock_plan = prior.read(phase.panel.REPORT / "plan.json")
    if missing or not plan["full_requested"] or plan["source"]["stock"] != stock_plan["source"]:
        raise ValueError("phase support must seal a complete replay with the shared native closure")
    selected = [r for r in records if r["policy"] == "causal" and r["recording"] == r["id"]]
    prior.roster_matches([r["id"] for r in selected], inputs, "causal phase roof")
    roof = {row["id"]: row for row in selected}
    for ident, row in roof.items():
        verify_native(ident, row, joint[ident], ADAPTIVE, "same_exact_backend")
    lock = prior.read(folder / "prediction-lock.json")
    files = {
        filename: prior.sha(folder / filename)
        for filename in ("predictions.jsonl.gz", "plan.json", "run-receipt.json")
    }
    receipt = prior.ledger_entry(
        folder,
        "predictions.jsonl.gz",
        "prediction-lock.json",
        dict(files=files, run=prior.read(folder / "run-receipt.json")),
    )
    return roof, receipt | {"attempted": lock["attempted"]}


def scores(refs, methods):
    for ident, ref in sorted(refs.items()):
        for arm in ARMS:
            original = ref["reference"]
            baseline = distance_km(original["baseline"][arm]["latlon"], ref["truth"])
            for name in (*ROLES, *methods):
                boundary = "original-v5-archive"
                if name in ROLES:
                    point = original[name][arm]
                    status, elapsed = point["status"], point["wall_s"]
                else:
                    row = methods[name][ident]
                    result = row["result"]
                    point = result["arms"][arm]
                    status, elapsed = result["status"], row.get("worker_wall_s")
                    boundary = row.get("source", "fresh_native_replay")
                error = distance_km(point["latlon"], ref["truth"])
                yield dict(
                    id=ident,
                    dataset=ref["group"],
                    method=name,
                    arm=arm,
                    status=status,
                    error_km=error,
                    forced_error_km=distance_km(point.get("forced_latlon"), ref["truth"]),
                    conditional_rms_hz=point.get("rf_rms_hz"),
                    timing_origin=boundary,
                    recorded_wall_s=elapsed,
                    within_v5_5pct=prior.paired_threshold(error, baseline, 1.05),
                    within_v5_10pct=prior.paired_threshold(error, baseline, 1.10),
                )


def curve_crossings(first, second):
    """Return half-open intervals with a strict CDF lead, on the common offered denominator."""
    a, b = (
        sorted(r["error_km"] for r in group if r["error_km"] is not None)
        for group in (first, second)
    )
    if len(first) != len(second):
        raise ValueError("CDF comparison requires the same offered denominator")
    ranges = []
    previous = 0
    for x in sorted(set(a) | set(b)):
        delta = bisect_right(a, x) - bisect_right(b, x)
        direction = (delta > 0) - (delta < 0)
        if direction != previous:
            if previous:
                ranges[-1]["end_km"] = x
            if direction:
                ranges.append(
                    dict(leader="first" if direction > 0 else "second", begin_km=x, end_km=None)
                )
            previous = direction
    return dict(
        strict_leads=ranges,
        lead_changes=sum(x["leader"] != y["leader"] for x, y in pairwise(ranges)),
    )


def subsets(rows):
    return {
        "published": {r["id"] for r in rows if r["error_km"] is not None},
        "within_5km": {r["id"] for r in rows if r["error_km"] is not None and r["error_km"] <= 5},
        **{k: {r["id"] for r in rows if r[k]} for k in ("within_v5_5pct", "within_v5_10pct")},
    }


def analyze(rows, methods):
    summaries, crossings = [], []
    names = (*ROLES, *methods)
    for dataset in ("all", "DS26", "DS29"):
        for arm in ARMS:
            groups = {name: [] for name in names}
            for row in rows:
                if row["arm"] == arm and (dataset == "all" or row["dataset"] == dataset):
                    groups[row["method"]].append(row)
            sets = {name: subsets(group) for name, group in groups.items()}
            for name, group in groups.items():
                errors = [r["error_km"] for r in group]
                summaries.append(
                    dict(
                        dataset=dataset,
                        arm=arm,
                        method=name,
                        offered=len(group),
                        published=len(sets[name]["published"]),
                        counts_within_km=thresholds(errors),
                        published_error_km=distribution(errors),
                        forced_error_km=distribution(r["forced_error_km"] for r in group),
                        conditional_rms_hz=distribution(r["conditional_rms_hz"] for r in group),
                        recorded_wall_s={
                            source: distribution(
                                r["recorded_wall_s"] for r in group if r["timing_origin"] == source
                            )
                            for source in sorted({r["timing_origin"] for r in group})
                        },
                        within_v5_5pct=len(sets[name]["within_v5_5pct"]),
                        within_v5_10pct=len(sets[name]["within_v5_10pct"]),
                    )
                )
            for a, b in combinations(names, 2):
                crossings.append(
                    dict(
                        dataset=dataset,
                        arm=arm,
                        first=a,
                        second=b,
                        cdf=curve_crossings(groups[a], groups[b]),
                        sets={
                            key: dict(
                                shared=sorted(a_set & b_set),
                                first_only=sorted(a_set - b_set),
                                second_only=sorted(b_set - a_set),
                            )
                            for key, a_set in sets[a].items()
                            for b_set in (sets[b][key],)
                        },
                    )
                )
    return summaries, crossings


def build(output):
    refs, inventory = _frozen_roof()
    inputs = prior.full_roster(refs, inventory)
    compact, compact_ledger = prior.compact_predictions(inputs, refs, audit_archive=True)
    native, native_ledger = prior.native_predictions(inputs)
    joint = native[prior.JOINT]
    anchor, anchor_ledger = anchor_predictions(inputs, joint)
    adaptive, adaptive_ledger = phase_predictions(inputs, joint)
    methods = {
        prior.COMPACT: compact,
        prior.CLOCK: native[prior.CLOCK],
        anchored.METHOD: anchor,
        ADAPTIVE: adaptive,
    }
    for records in methods.values():
        for ident, row in records.items():
            prior.require_fields(row, {key: compact[ident][key] for key in MATCH})
    phase_scores.pack(
        output / POSITIONS, [row for group in methods.values() for row in group.values()]
    )
    rows = list(scores(refs, methods))
    csv_file(output / "scores.csv", rows)
    summaries, crossings = analyze(rows, methods)
    save_json(output / "summary.json", dict(roof=dict(DS26=127, DS29=8), series=summaries))
    save_json(output / "crossings.json", crossings)
    save_json(
        output / "sources.json",
        dict(
            methods={
                prior.COMPACT: compact_ledger,
                prior.CLOCK: native_ledger[prior.CLOCK],
                anchored.METHOD: anchor_ledger,
                ADAPTIVE: adaptive_ledger,
            },
            native_graph_control=native_ledger[prior.JOINT],
            audited_original_executions=True,
            frozen_corpus_sha256=prior.sha(corpus.FROZEN / "provenance.json"),
            aggregator_sha256=prior.sha(Path(__file__)),
        ),
    )
    save_json(
        output / "roof-lock.json",
        dict(
            cases=sorted(refs), files={filename: prior.sha(output / filename) for filename in FILES}
        ),
    )
    save_json(
        output / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id=CHART,
                    method=METHOD,
                    scope="roof",
                    cases="roof135",
                    title="Full receivers on 135 original roof recordings",
                    caption=(
                        "Same stored GLRT inputs, causal catalogue and supplied tile. The four "
                        "original v5 roles form the shaded range. Native variants rebuild the "
                        "anonymous Graph. Curves use all offered recordings as the denominator."
                    ),
                    seal="roof-lock.json",
                    provenance=list(FILES[1:]),
                    series=[
                        dict(
                            key=key,
                            label=label,
                            file=POSITIONS,
                            value=method,
                            **({"match": list(MATCH)} if key != "one" else {}),
                        )
                        for method, label, key in SERIES
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPORT)
    build(local_output(parser.parse_args().output))
