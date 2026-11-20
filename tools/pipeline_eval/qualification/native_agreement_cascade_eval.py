"""Verify and score a decision-driven native agreement cascade."""

import argparse
import gzip
from collections import Counter
from pathlib import Path
from statistics import mean

from ..__main__ import encoded, local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, distribution, thresholds
from ..variants import native_agreement_cascade as gate
from . import anchor_receiver_full as anchors
from . import full_receiver_comparison as common
from .broad_search_budget import frozen_inputs
from .full_receiver_refinement import anchor_predictions
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

REPORT = common.SCREEN / "recovery/cascade"
CLOCK = common.CLOCK
ANCHORS = anchors.METHOD
COMPACT = common.COMPACT
MATCH = ("input_sha256", "observation_sha256", "native_sha256", "catalog_sha256", "tile")
COMMON = MATCH[2:]
SENSITIVITY = (0.25, gate.LIMIT_KM, 1.0)
BOUND = common.SCREEN / "refinement/boundary-roof/primary"
NEAR = common.SCREEN / "refinement/anchor-near-edge"


def same_inputs(one, other, fields=MATCH):
    common.require_fields(one, {key: other[key] for key in fields})


def decisions(clock, anchor, threshold=gate.LIMIT_KM):
    common.roster_matches(clock, anchor, "native pair")
    result = {}
    for ident in sorted(clock):
        same_inputs(clock[ident], anchor[ident])
        if any(
            row[ident]["result"]["status"] not in ("ok", "withheld")
            or not row[ident]["observation_sha256"]
            for row in (clock, anchor)
        ):
            raise ValueError(f"{ident} lacks a completed matched native pair")
        result[ident] = gate.route(clock[ident]["result"], anchor[ident]["result"], threshold)
    return result


def compact_wall(row):
    key = {
        "fresh_full_panel": "worker_wall_s",
        "prior_timing": "prior_timing_worker_wall_s",
        "prior_confirmation": "prior_confirmation_worker_wall_s",
    }[row["source"]]
    return row[key]


def model(clock, anchor, compact, routes):
    records = []
    for ident, route in routes.items():
        smooth, curve, slow = (rows[ident] for rows in (clock, anchor, compact))
        same_inputs(smooth, slow, COMMON)
        fallback = route["route"] == "fallback"
        pair_wall = smooth["worker_wall_s"] + curve["worker_wall_s"]
        slow_wall = compact_wall(slow)
        point = (slow if fallback else smooth)["result"]
        records.append(
            dict(
                **{key: smooth[key] for key in ("id", *MATCH)},
                cohort="roof",
                method=gate.METHOD,
                result=dict(
                    point, boundary="Sealed paired native route with matched compact fallback model"
                ),
                route=route,
                compact_timing_origin=slow["source"],
                modeled_serial_wall_s=pair_wall + fallback * slow_wall,
                native_wall_s=pair_wall,
                compact_wall_s=slow_wall,
                native_cpu_s=sum(row["worker"]["cpu_s"] for row in (smooth, curve)),
            )
        )
    return records


def time_model(records):
    fast = [row for row in records if row["route"]["route"] == "fast"]
    saw = sum(r["modeled_serial_wall_s"] for r in records)
    bare = sum(r["compact_wall_s"] for r in records)
    return dict(
        attempts=len(records),
        fast=len(fast),
        fallback=len(records) - len(fast),
        route_reasons=dict(Counter(row["route"]["reason"] for row in records)),
        serial_wall_total_s=saw,
        compact_wall_total_s=bare,
        serial_wall_ratio=saw / bare,
        serial_wall_s=distribution(r["modeled_serial_wall_s"] for r in records),
        compact_wall_s=distribution(r["compact_wall_s"] for r in records),
        compact_wall_avoided_s=sum(r["compact_wall_s"] for r in fast),
        extra_native_cpu_total_s=sum(r["native_cpu_s"] for r in records),
        extra_native_cpu_per_record_s=mean(r["native_cpu_s"] for r in records),
        native_serial_wall_total_s=sum(r["native_wall_s"] for r in records),
        compact_cpu_s=None,
    )


def scores(rows, refs):
    for row in rows:
        ref = refs[row["id"]]
        for arm in ARMS:
            point = row["result"]["arms"][arm]
            error = distance_km(point["latlon"], ref["truth"])
            baseline = ref["reference"]["baseline"][arm]["error_km"]
            yield dict(
                id=row["id"],
                dataset=ref["group"],
                method=row["method"],
                arm=arm,
                route=row.get("route", {}).get("route"),
                status=row["result"]["status"],
                published_error_km=error,
                within_v5_10pct=common.paired_threshold(error, baseline, 1.10),
                original_v5_error_km=baseline,
                conditional_rms_hz=point.get("rf_rms_hz"),
                model_serial_wall_s=row.get("modeled_serial_wall_s"),
                modeled_native_cpu_s=row.get("native_cpu_s"),
                arm_agreement_km=row.get("route", {}).get("agreement_km", {}).get(arm),
            )


def distribution_rows(table):
    groups = []
    for method in sorted({r["method"] for r in table}):
        for dataset in ("all", "DS26", "DS29"):
            for arm in ARMS:
                group = [
                    r
                    for r in table
                    if r["method"] == method
                    and r["arm"] == arm
                    and (dataset == "all" or r["dataset"] == dataset)
                ]
                errors = [r["published_error_km"] for r in group]
                groups.append(
                    dict(
                        method=method,
                        dataset=dataset,
                        arm=arm,
                        offered=len(group),
                        statuses=dict(Counter(r["status"] for r in group)),
                        within_km=thresholds(errors),
                        error_km=distribution(errors),
                        within_v5_10pct=sum(r["within_v5_10pct"] for r in group),
                        conditional_rms_hz=distribution(r["conditional_rms_hz"] for r in group),
                    )
                )
    return groups


def verified_rows(folder, name="positions.jsonl.gz"):
    seal = common.seal(folder, "prediction-lock.json", (name,))
    rows = read_predictions(folder / name)
    common.roster_matches(rows, seal["cases"], folder.name)
    return rows, seal


def shifted_pairs():
    clock, clock_lock = verified_rows(BOUND, f"{CLOCK}.jsonl.gz")
    anchor, anchor_lock = verified_rows(NEAR)
    request_path = BOUND / "requests.json"
    if common.sha(request_path) != anchor_lock["requests_sha256"]:
        raise ValueError("shifted native workers used different request authority")
    plan = common.read(request_path)
    if (
        plan["evaluator_sha256"] != clock_lock["evaluator_sha256"]
        or common.sha(BOUND / "evaluator.json") != plan["evaluator_sha256"]
    ):
        raise ValueError("shifted-offer scorer differs from the shared request authority")
    if common.sha(NEAR / "source-lock.json") != anchor_lock["source_lock_sha256"]:
        raise ValueError("shifted anchor source seal changed")
    archive_routes = decisions(clock, anchor)
    queries = common.read(BOUND / "evaluator.json")["labels"]
    common.roster_matches([row["id"] for row in queries], clock, "shifted evaluator")
    wanted = [row for row in queries if row["condition"] in ("near-outside", "six-outside")]
    if len(wanted) != 20:
        raise ValueError("expected twenty deliberately excluded shifted tiles")
    return transfer(clock, anchor, archive_routes, wanted, "shifted-omitted")


def original_omissions():
    native_clock = common.native_clock_full.REPORT
    clock, _ = verified_rows(native_clock)
    anchor, _ = verified_rows(anchors.REPORT)
    one, two = (
        {key: row for key, row in rows.items() if row["cohort"] == "omitted"}
        for rows in (clock, anchor)
    )
    routes = decisions(one, two)
    lock = common.seal(native_clock, "omitted-figure-lock.json", ("omitted-queries.json",))
    queries = common.read(native_clock / "omitted-queries.json")["queries"]
    common.roster_matches([q["id"] for q in queries], lock["cases"], "omitted query")
    return transfer(one, two, routes, queries, "archived-omitted")


def transfer(clock, anchor, routes, source_queries, cohort):
    rows, queries = [], []
    for source in source_queries:
        ident = source["id"]
        a, b, choice = clock[ident], anchor[ident], routes[ident]
        common.require_fields(
            a, {key: source[key] for key in ("recording", "tile", "input_sha256") if key in source}
        )
        common.require_fields(a, source.get("bindings", {}))
        det = {key: a[key] for key in ("id", "recording", *MATCH)}
        fast = choice["route"] == "fast"
        candidate = (
            a["result"]
            if fast
            else dict(
                status="unavailable",
                reason="compact_fallback_unmeasured_for_this_tile",
                metrics={},
                arms={arm: dict(latlon=None) for arm in ARMS},
                boundary=gate.BOUNDARY,
            )
        )
        rows.extend(
            [
                dict(det, method=gate.METHOD, result=candidate, cohort=cohort, route=choice),
                dict(det, method=CLOCK, result=a["result"], cohort=cohort),
                dict(det, method=ANCHORS, result=b["result"], cohort=cohort),
            ]
        )
        queries.append(
            dict(
                id=ident,
                recording=a["recording"],
                truth=source["truth"],
                condition={
                    "near-outside": "Site 1–2 km outside",
                    "six-outside": "Site 6 km outside",
                }.get(source["condition"], source["condition"]),
                bindings={key: a[key] for key in MATCH},
            )
        )
    summary = {
        label: dict(
            offered=sum(q["condition"] == label for q in queries),
            statuses=dict(
                Counter(
                    r["result"]["status"]
                    for r, q in zip(rows[::3], queries, strict=True)
                    if q["condition"] == label
                )
            ),
            smooth_publications=sum(
                r["result"]["status"] == "ok" and q["condition"] == label
                for r, q in zip(rows[1::3], queries, strict=True)
            ),
            anchor_publications=sum(
                r["result"]["status"] == "ok" and q["condition"] == label
                for r, q in zip(rows[2::3], queries, strict=True)
            ),
        )
        for label in sorted({q["condition"] for q in queries})
    }
    return rows, queries, summary


def fresh_rows(paths, routes, clock, anchor, compact):
    if not paths:
        return [], []
    rows, receipts = [], []
    for route, work in zip(("fast", "fallback"), paths, strict=True):
        path = work / "cascade.json"
        measured = common.read(path)
        ident = next(i for i, d in routes.items() if i.startswith("DS26-") and d["route"] == route)
        common.require_fields(measured, dict(id=ident, route=routes[ident]))
        expected_fast = ["smooth-clock", "curve-anchors"]
        calls = expected_fast + (["compact-secant"] if route == "fallback" else [])
        common.require_fields(
            measured, dict(calls=calls, request_sha256=clock[ident]["input_sha256"])
        )
        for method, rows_by_id in (("smooth", clock), ("anchors", anchor)):
            candidate, old = measured[method], rows_by_id[ident]
            common.require_fields(
                candidate, {k: old[k] for k in ("input_sha256", "observation_sha256")}
            )
            common.require_fields(
                candidate["result"], {k: old["result"].get(k) for k in ("status", "reason", "arms")}
            )
        control_path = work / "compact-only.json"
        control = common.read(control_path) if control_path.is_file() else measured["compact"]
        if control is None:
            raise ValueError("expected separate successful compact control for the fresh fast path")
        if control["result"]["status"] != "ok":
            raise ValueError("fresh compact control did not return a measured position")
        for arm in ARMS:
            actual = control["result"]["arms"][arm]["latlon"]
            old = compact[ident]["result"]["arms"][arm]["latlon"]
            if distance_km(actual, old) != 0:
                raise ValueError(f"{ident} fresh compact endpoint differs from its sealed control")
        published = measured["result"]
        selected = measured["smooth"]["result"] if route == "fast" else control["result"]
        common.require_fields(published, {k: selected.get(k) for k in ("status", "reason", "arms")})
        key = {k: clock[ident][k] for k in ("id", *COMMON)}
        rows.extend(
            [
                dict(
                    key, cohort="fresh", method=gate.METHOD, route=routes[ident], result=published
                ),
                dict(key, cohort="fresh", method=COMPACT, result=control["result"]),
            ]
        )
        receipts.append(
            dict(
                id=ident,
                measurement=measured,
                compact_control=control,
                control_origin="separate same-core run"
                if control_path.is_file()
                else "selected fallback stage",
                historical_compact=compact[ident]["result"]["arms"],
            )
        )
    return rows, receipts


def publish(output, records, queries_by_group):
    filename, charts = "positions.jsonl.gz", []
    write(
        output / filename, gzip.compress(b"".join(encoded(row) + b"\n" for row in records), mtime=0)
    )
    files = {name: common.sha(output / name) for name in (filename, "routing.json", "sources.json")}
    specs = (
        ("roof", "Full roof · native agreement and compact fallback", (COMPACT, CLOCK, ANCHORS)),
        ("fresh", "Live native cascade · fast and fallback branches", (COMPACT,)),
        ("shifted-omitted", "Native agreement on shifted tiles excluding truth", (CLOCK, ANCHORS)),
        ("archived-omitted", "Native agreement on archived omitted tiles", (CLOCK, ANCHORS)),
    )
    labels = {COMPACT: "Compact secant", CLOCK: "Smooth clock", ANCHORS: "Curve anchors"}
    for group, title, controls in specs:
        selected = [r["id"] for r in records if r["method"] == gate.METHOD and r["cohort"] == group]
        if not selected:
            continue
        transfer = group in queries_by_group
        seal = f"{group}-figure-lock.json"
        s = dict(where=dict(cohort=group), file=filename)
        caption = {
            "roof": (
                "Routing uses both native positions. Compact fallback positions use the verified "
                "matching original-tile replay."
            ),
            "fresh": (
                "Two real native-start runs selected only by the route. Compact ran on demand "
                "for the fallback and independently for the fast case."
            ),
            "shifted-omitted": (
                "Both native methods ran at each supplied wrong tile. The trusted original-tile "
                "compact fallback is unavailable here."
            ),
            "archived-omitted": (
                "Both native methods measured decisions at the omitted offers. Compact fallback "
                "outcomes remain unmeasured here."
            ),
        }[group]
        spec = dict(
            id=f"{gate.METHOD}-{group}",
            method=gate.METHOD,
            scope="transfer" if transfer else "roof",
            cases=selected,
            title=title,
            caption=caption,
            seal=seal,
            provenance=["sources.json", "routing.json"],
            series=[
                dict(
                    key="candidate" if transfer else "one",
                    label="Native cascade",
                    value=gate.METHOD,
                    **s,
                )
            ],
        )
        keys = ("stock", "one") if transfer else ("stock", "one_native_factors", "all_visits")
        match = MATCH if transfer else COMMON
        spec["series"].extend(
            dict(key=key, label=labels[control], value=control, match=list(match), **s)
            for key, control in zip(keys, controls, strict=False)
        )
        sealed = dict(files)
        if group == "fresh":
            receipt = "fresh-receipts.json"
            sealed[receipt] = common.sha(output / receipt)
            spec["provenance"].append(receipt)
        if transfer:
            name = f"{group}-queries.json"
            save_json(output / name, dict(queries=queries_by_group[group]))
            sealed[name] = common.sha(output / name)
            spec["queries"] = name
        save_json(output / seal, dict(cases=selected, files=sealed))
        charts.append(spec)
    save_json(output / "figures.json", dict(version=1, charts=charts))


def compare(output, live_paths):
    inputs = frozen_inputs()
    natives, ledger = common.native_predictions(inputs)
    clock = natives[CLOCK]
    anchor, anchor_ledger = anchor_predictions(inputs, natives[common.JOINT])
    routes = decisions(clock, anchor)
    save_json(output / "routing.json", dict(primary_threshold_km=gate.LIMIT_KM, decisions=routes))
    refs, _ = _frozen_roof()
    compact, compact_ledger = common.compact_predictions(inputs, refs)
    roof = model(clock, anchor, compact, routes)
    roof_parents = [
        dict(r, cohort="roof") for group in (compact, clock, anchor) for r in group.values()
    ]
    rows = list(scores(roof + roof_parents, refs))
    csv_file(output / "errors.csv", rows)
    shifted_rows, shifted_queries, shifted = shifted_pairs()
    archive_rows, archive_queries, archive = original_omissions()
    measured, receipts = fresh_rows(live_paths, routes, clock, anchor, compact)
    measured_table = list(scores(measured, refs))
    if measured:
        save_json(output / "fresh-receipts.json", receipts)
        csv_file(output / "fresh-errors.csv", measured_table)
    sensitivity = []
    for limit in SENSITIVITY:
        variant = model(clock, anchor, compact, decisions(clock, anchor, limit))
        accuracy = distribution_rows(list(scores(variant, refs)))
        sensitivity.append(
            dict(
                threshold_km=limit,
                **time_model(variant),
                all_roof_scores=[item for item in accuracy if item["dataset"] == "all"],
            )
        )
    save_json(
        output / "summary.json",
        dict(
            roof=distribution_rows(rows),
            primary_work=time_model(roof),
            descriptive_sensitivity=sensitivity,
            prior_wrong_offers=dict(shifted=shifted, archived=archive),
            fresh=distribution_rows(measured_table) if measured else [],
        ),
    )
    save_json(
        output / "sources.json",
        dict(
            native_clock=ledger[CLOCK],
            curve_anchors=anchor_ledger,
            compact=compact_ledger,
            protocol=common.sha(REPORT / "PROTOCOL.md"),
            router=common.sha(Path(gate.__file__)),
            evaluator=common.sha(Path(__file__)),
            live_runner=common.sha(Path(__file__).with_name("native_agreement_cascade_fresh.py")),
            near_edge_locks={
                str(p.relative_to(common.ROOT)): common.sha(p)
                for p in (BOUND / "prediction-lock.json", NEAR / "prediction-lock.json")
            },
        ),
    )
    publish(
        output,
        roof + roof_parents + measured + shifted_rows + archive_rows,
        {"shifted-omitted": shifted_queries, "archived-omitted": archive_queries},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPORT)
    parser.add_argument("--fresh", type=Path, nargs=2, metavar=("FAST", "FALLBACK"))
    args = parser.parse_args()
    compare(local_output(args.out), args.fresh)


if __name__ == "__main__":
    main()
