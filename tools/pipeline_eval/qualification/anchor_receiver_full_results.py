"""Seal and score native anchor predictions against equal-input stock and the v5 archives."""

import argparse
from collections import Counter
from pathlib import Path

from ..__main__ import read_predictions, save_json, write
from ..scoring import ARMS, distance_km, distribution
from . import anchor_receiver_full as full
from . import native_joint_full_results as native
from .fresh_scenes import _read, _sha
from .native_joint_results import geodata
from .prefix_figures import csv_file

FILE = native.PREDICTIONS
STOCK_FILE = "stock-positions.jsonl.gz"
MATCH = ["native_sha256", "catalog_sha256", "input_sha256"]


def matched_stock(predictions, plan):
    archive = full.STOCK / "prediction-lock.json"
    if _sha(archive) != plan["stock_prediction_lock_sha256"]:
        raise ValueError("archived native stock changed since planned inference")
    full.old.base.secant_full._verify_files(full.STOCK, _read(archive)["files"])
    stock = read_predictions(full.STOCK / FILE)
    if stock.keys() != predictions.keys():
        raise ValueError("stock roster differs from native anchor roster")
    valid = 0
    for ident, row in predictions.items():
        control = stock[ident]
        if any(row[k] != control[k] for k in (*MATCH, "tile", "recording", "cohort")):
            raise ValueError(f"{ident} is not the identical native control request")
        projection = row.get("observation_sha256")
        if projection and control.get("observation_sha256"):
            if projection != control["observation_sha256"]:
                raise ValueError(f"{ident} changed the same-input Graph projection")
            valid += 1
    return stock, valid


def _summary(rows):
    return dict(
        scheduled=len(rows),
        statuses=dict(Counter(r["status"] for r in rows)),
        published=sum(r["error_km"] is not None for r in rows),
        within_5km=sum(r["error_km"] is not None and r["error_km"] <= 5.0 for r in rows),
        **{
            key: distribution(r[key] for r in rows)
            for key in (
                "error_km",
                "forced_error_km",
                "conditional_rms_hz",
                "associated_observations",
                "worker_wall_s",
                "worker_cpu_s",
                "peak_rss_kib",
                "vm_peak_kib",
                "true_tile_margin_km",
            )
        },
    )


def _prepared(predictions, refs):
    small = full.prepared.REPORT
    lock = _read(small / "prediction-lock.json")
    if _sha(small / full.prepared.FILE) != lock["files"][full.prepared.FILE]:
        raise ValueError("prepared anchor evidence changed")
    import gzip
    import json

    rows = []
    with gzip.open(small / full.prepared.FILE, "rt") as stream:
        for row in map(json.loads, stream):
            if row["method"] != full.prepared.METHODS[0] or row["cohort"] == "omitted":
                continue
            actual = predictions[row["id"]]
            if any(row[k] != actual[k] for k in ("native_sha256", "catalog_sha256", "tile")):
                raise ValueError("prepared/native paired offer or recording differs")
            truth = refs[row["id"]]["truth"]
            for arm in ARMS:
                one, two = row["result"], actual["result"]
                rows.append(
                    dict(
                        id=row["id"],
                        arm=arm,
                        same_projected_digest=row["observation_sha256"]
                        == actual.get("observation_sha256"),
                        prepared_status=one["status"],
                        native_status=two["status"],
                        prepared_error_km=distance_km(one["arms"][arm]["latlon"], truth),
                        native_error_km=distance_km(two["arms"][arm]["latlon"], truth),
                        prepared_points=one["metrics"].get("associated_observations"),
                        native_points=two["metrics"].get("associated_observations"),
                    )
                )
    return dict(source_prediction_sha256=lock["files"][full.prepared.FILE], cases=rows)


def figures(output, predictions, queries, lock):
    files = lock["files"] | {
        STOCK_FILE: _sha(output / STOCK_FILE),
        "stock-original-prediction-lock.json": _sha(output / "stock-original-prediction-lock.json"),
    }
    charts = []
    for cohort in ("roof", "omitted"):
        transfer = cohort == "omitted"
        names = [k for k, r in predictions.items() if r["cohort"] == cohort]
        additional = {}
        bindings = dict(files)
        if transfer:
            query_file = "omitted-queries.json"
            save_json(output / query_file, {"queries": queries})
            bindings[query_file] = _sha(output / query_file)
            additional["queries"] = query_file
        seal = f"{cohort}-figure-lock.json"
        save_json(output / seal, dict(cases=names, files=bindings))
        charts.append(
            dict(
                id=f"native-anchor-full-{cohort}",
                method=full.METHOD,
                title="Independent anchors · full native roof"
                if not transfer
                else "Independent anchors · nine omitted regions",
                caption="Matched native GLRT factors through the same streaming Graph and TLE.",
                scope="transfer" if transfer else "roof",
                cases=names if transfer else "roof135",
                seal=seal,
                provenance=["plan.json", "stock-original-prediction-lock.json"],
                series=[
                    dict(
                        key="candidate" if transfer else "one",
                        label="Streamed orbit anchors",
                        file=FILE,
                        value=full.METHOD,
                        where={"cohort": cohort},
                    ),
                    dict(
                        key="stock",
                        label="Archived native joint",
                        file=STOCK_FILE,
                        value=full.old.base.METHOD,
                        where={"cohort": cohort},
                        match=MATCH,
                    ),
                ],
                **additional,
            )
        )
    save_json(output / "figures.json", dict(version=1, charts=charts))


def score(work, bundle, output):
    native.seal(work, bundle, output, prepare=full.prepare, method=full.METHOD)
    lock = _read(output / "prediction-lock.json")
    plan = _read(output / "plan.json")
    predictions = read_predictions(output / FILE)
    stock, exact_projections = matched_stock(predictions, plan)
    rows, queries = native.matched_score_rows(predictions, plan, solver_stage="anchor_backend")
    refs = {
        r["id"]: r
        for panel in ("ds26-common127", "roof16")
        for r in native.phase.corpus.references(panel)
    }
    stock_rows = []
    for row in rows:
        ident, arm = row["id"], row["arm"]
        candidate = predictions[ident]
        metrics = candidate["result"]["metrics"]
        for key in ("provisional_anchors", "anchor_tracks", "orbit_families", "anchor_held_rms_hz"):
            row[key] = metrics.get(key)
        matched = stock[ident]
        control = geodata(matched, arm, refs[row["recording"]]["truth"])
        original = {
            k: row[k]
            for k in ("id", "recording", "cohort", "dataset", "arm", "true_tile_margin_km")
        }
        control["associated_observations"] = matched["result"]["metrics"].get(
            "associated_observations"
        )
        stock_rows.append(original | control)
    grouped = []
    for cohort in ("roof", "omitted"):
        for dataset in ("all", "DS26", "DS29"):
            for arm in ARMS:

                def select(sample, cohort=cohort, arm=arm, dataset=dataset):
                    return [
                        r
                        for r in sample
                        if r["cohort"] == cohort
                        and r["arm"] == arm
                        and (dataset == "all" or r["dataset"] == dataset)
                    ]

                anchor, stock_samples = select(rows), select(stock_rows)
                if not anchor:
                    continue
                old = {r["id"]: r for r in stock_samples}
                paired = [
                    r["error_km"] - old[r["id"]]["error_km"]
                    for r in anchor
                    if r["error_km"] is not None and old[r["id"]]["error_km"] is not None
                ]
                grouped.append(
                    dict(
                        cohort=cohort,
                        dataset=dataset,
                        arm=arm,
                        anchor=_summary(anchor),
                        native_joint=_summary(stock_samples),
                        paired_anchor_minus_joint_km=distribution(paired),
                    )
                )
    csv_file(output / "scores.csv", rows)
    csv_file(output / "stock-scores.csv", stock_rows)
    save_json(
        output / "summary.json",
        dict(
            groups=grouped,
            replay=lock["run"],
            identical_graph_projection_count=exact_projections,
            published_c_ablation=native.ablation(rows),
            archive_reference_groups=native.summarize(rows),
            prepared_comparison=_prepared(predictions, refs),
        ),
    )
    write(output / STOCK_FILE, (full.STOCK / FILE).read_bytes())
    write(
        output / "stock-original-prediction-lock.json",
        (full.STOCK / "prediction-lock.json").read_bytes(),
    )
    figures(output, predictions, queries, lock)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, default=full.old.base.BUNDLE)
    parser.add_argument("--output", type=Path, default=full.REPORT)
    args = parser.parse_args()
    score(args.work, args.bundle, args.output)
