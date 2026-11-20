"""Score the frozen halo vote and earlier exact-asset omission comparators."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from ..__main__ import read_predictions, save_json, write
from ..scoring import ARMS, distance_km, distribution, thresholds
from . import native_joint_full_results as shared
from . import region_halo_trial as trial

phase = trial.phase
CANDIDATE, STOCK = trial.METHOD, trial.clock.METHOD
CONDITIONS = dict(
    centered="Centered",
    **{
        "near-inside": "Near inside",
        "near-outside": "Near omission",
        "far-outside": "Far omission",
    },
)


def old_compatible(path, bound, truth, expected):
    rows = phase._read(path)
    matched = [r for r in rows if r["id"] == bound["id"] and r["method"] == expected]
    (row,) = matched
    if any(row[k] != bound[k] for k in ("native_sha256", "catalog_sha256", "tile")):
        raise ValueError("majority diagnostics used different native, catalogue or geometry")
    return row, method_record(row, truth)


def method_record(row, truth):
    return dict(
        method=row["method"],
        status=row["result"]["status"],
        arms={
            arm: dict(
                error_km=distance_km(point.get("latlon"), truth), rf_rms_hz=point.get("rf_rms_hz")
            )
            for arm, point in row["result"]["arms"].items()
        },
    )


def related(records, labels):
    results = {}
    roof = trial.exterior.REPORT / "diagnostic-stress"
    recenter = trial.exterior.recenter.REPORT / "diagnosed-stress"
    influence = trial.REPORT.parent.parent / "redesign/orbit-influence/diagnostic-stress"
    for folder, methods in (
        (roof, (STOCK, trial.exterior.METHOD)),
        (recenter, ("native_recenter_verify",)),
        (influence, ("native_smooth_orbit_influence",)),
    ):
        lock = phase._read(folder / "prediction-lock.json")
        trial.clock.base.secant_full._verify_files(folder, lock["files"])
        for method in methods:
            indexed = read_predictions(folder / f"{method}.jsonl.gz")
            for ident, shown in records.items():
                old = indexed.get(ident)
                if shown["cohort"] != "archived-roof" or old is None:
                    continue
                if any(
                    shown[k] != old[k]
                    for k in ("input_sha256", "native_sha256", "catalog_sha256", "tile")
                ):
                    raise ValueError("earlier roof comparator changed a native binding")
                if (
                    shown.get("observation_sha256")
                    and old.get("observation_sha256") != shown["observation_sha256"]
                ):
                    raise ValueError("earlier roof comparator has a different Graph")
                if (
                    method == STOCK
                    and "initial" in shown
                    and any(
                        shown["initial"].get(k) != old["result"].get(k)
                        for k in ("arms", "status", "reason")
                    )
                ):
                    raise ValueError("integrated first fit differs from standalone archived smooth")
                results.setdefault(ident, []).append(method_record(old, labels[ident]["truth"]))
    extra = {}
    if trial.majority.NEAR in records:
        near = records[trial.majority.NEAR]
        ident, truth = near["id"], labels[near["id"]]["truth"]
        folder = trial.majority.REPORT
        seal = phase._read(folder / "prediction-lock.json")
        trial.clock.base.secant_full._verify_files(folder, seal["files"])
        row, report = old_compatible(
            folder / "predictions.json", near, truth, trial.majority.METHOD
        )
        results[ident] = [report]
        extra[ident] = row
        subscan = folder.with_name("edge-interval")
        figure = phase._read(subscan / "measured-figure-lock.json")
        trial.clock.base.secant_full._verify_files(subscan, figure["files"])
        with gzip.open(subscan / "figure-positions.jsonl.gz", "rt") as stream:
            for old in map(json.loads, stream):
                if old["id"] != ident or old["method"] != "v5_secant_subscan_interval":
                    continue
                if old["native_sha256"] != row["original_factor_sha256"] or any(
                    old[k] != row[k] for k in ("catalog_sha256", "tile", "history_sha256")
                ):
                    raise ValueError("subscan does not share the archived input factor authority")
                results[ident].append(method_record(old, truth))
    return results, extra


def score_rows(records, labels):
    rows = []
    for ident, row in records.items():
        target = labels[ident]
        base = row.get("initial", row["result"])
        halo = row.get("halo", {})
        vote = row.get("halo_vote", {})
        for arm in ARMS:
            original = base["arms"][arm]
            published = row["result"]["arms"][arm]
            full = halo.get("arms", {}).get(arm, {})
            fitted = full.get("forced_latlon")
            rows.append(
                dict(
                    id=ident,
                    cohort=row["cohort"],
                    recording=row["recording"],
                    source=target["source_label"],
                    condition=target["condition"],
                    truth_margin_km=target["margin_km"],
                    arm=arm,
                    initial_status=base["status"],
                    initial_reason=base.get("reason"),
                    initial_error_km=distance_km(original.get("latlon"), target["truth"]),
                    initial_forced_error_km=distance_km(
                        original.get("forced_latlon"), target["truth"]
                    ),
                    initial_rf_rms_hz=original.get("rf_rms_hz"),
                    status=row["result"]["status"],
                    reason=row["result"].get("reason"),
                    error_km=distance_km(published.get("latlon"), target["truth"]),
                    halo_status=halo.get("status"),
                    halo_reason=halo.get("reason"),
                    halo_error_km=distance_km(fitted, target["truth"]),
                    halo_signed_margin_km=shared.roi_margin(fitted, row["tile"]),
                    halo_nominal_radius_km=full.get("radius_km"),
                    halo_rf_rms_hz=full.get("rf_rms_hz"),
                    vote=vote.get("state"),
                    vote_reason=vote.get("reason"),
                    exterior_face=vote.get("exterior_face"),
                    supported_outside_distance_km=vote.get("robust_outside_distance_km"),
                    supported_inside_distance_km=vote.get("robust_inside_distance_km"),
                    worker_wall_s=row.get("worker_wall_s"),
                    initial_fit_wall_s=(row.get("initial_fit_time") or {}).get("wall_s"),
                    halo_fit_wall_s=(row.get("halo_fit_time") or {}).get("wall_s"),
                    folds_wall_s=(row.get("fold_time") or {}).get("wall_s"),
                    worker_cpu_s=(row.get("worker") or {}).get("cpu_s"),
                    peak_rss_kib=row.get("resident_peak_kib"),
                    vm_peak_kib=(row.get("proc_memory_kib") or {}).get("VmPeak"),
                )
            )
    return rows


def summarize(rows):
    summary = []
    for cohort in ("fresh-synthetic", "archived-roof", "archived-majority"):
        for arm in ARMS:
            group = [r for r in rows if r["cohort"] == cohort and r["arm"] == arm]
            if not group:
                continue
            for key, select in (
                ("all", group),
                ("containing", [r for r in group if r["truth_margin_km"] > 0]),
                ("omitted", [r for r in group if r["truth_margin_km"] < 0]),
                *((name, [r for r in group if r["condition"] == name]) for name in CONDITIONS),
            ):
                if not select:
                    continue
                errors = [r["error_km"] for r in select]
                summary.append(
                    dict(
                        cohort=cohort,
                        arm=arm,
                        condition=key,
                        scheduled=len(select),
                        recording_count=len({r["recording"] for r in select}),
                        decisions=dict(Counter(r["status"] for r in select)),
                        initial_decisions=dict(Counter(r["initial_status"] for r in select)),
                        halo_decisions=dict(Counter(r["halo_status"] for r in select)),
                        vote=dict(Counter(r["vote"] for r in select)),
                        full_halo_outside=sum(
                            r["halo_signed_margin_km"] is not None
                            and r["halo_signed_margin_km"] < 0
                            for r in select
                        ),
                        position_error_km=distribution(errors),
                        within_km=thresholds(errors),
                        **{
                            k: distribution(r[k] for r in select)
                            for k in (
                                "initial_error_km",
                                "initial_rf_rms_hz",
                                "halo_error_km",
                                "halo_rf_rms_hz",
                                "halo_signed_margin_km",
                                "worker_wall_s",
                                "worker_cpu_s",
                                "initial_fit_wall_s",
                                "halo_fit_wall_s",
                                "folds_wall_s",
                                "peak_rss_kib",
                                "vm_peak_kib",
                            )
                        },
                    )
                )
    return summary


def manifest(output, records, labels, archived_comparator, lock):
    for scope in ("fresh-synthetic", "archived-roof", "archived-majority"):
        group = [r for r in records.values() if r["cohort"] == scope]
        if not group:
            continue
        folder = output / scope
        files = {}
        stock = [dict(r, method=STOCK, result=r.get("initial", r["result"])) for r in group]
        plotting = [
            dict(
                r,
                result=dict(
                    r["result"],
                    arms={
                        arm: dict(
                            point,
                            forced_latlon=r.get("halo", {})
                            .get("arms", {})
                            .get(arm, {})
                            .get("forced_latlon"),
                        )
                        for arm, point in r["result"]["arms"].items()
                    },
                ),
            )
            for r in group
        ]
        for selected, method in ((plotting, CANDIDATE), (stock, STOCK)):
            name = f"{method}.jsonl.gz"
            files[name] = shared.pack(folder, name, selected)
        queries = []
        for row in group:
            target = labels[row["id"]]
            bindings = {k: row[k] for k in ("native_sha256", "catalog_sha256")}
            queries.append(
                dict(
                    id=row["id"],
                    condition=target["condition"],
                    recording=target["source_label"],
                    truth=target["truth"],
                    bindings=bindings,
                )
            )
        save_json(folder / "figure-queries.json", dict(queries=queries))
        files["figure-queries.json"] = phase.digest(folder / "figure-queries.json")
        cases = [r["id"] for r in group]
        plots = [
            dict(
                key="candidate",
                label="Orbit-split halo veto",
                file=f"{CANDIDATE}.jsonl.gz",
                value=CANDIDATE,
                forced_label="Halo · forced",
            ),
            dict(
                key="stock",
                label="Native smooth",
                file=f"{STOCK}.jsonl.gz",
                value=STOCK,
                forced_label="Smooth · forced",
                match=["input_sha256", "tile"],
            ),
        ]
        if scope == "archived-majority":
            method = trial.majority.METHOD
            name = f"{method}.jsonl.gz"
            files[name] = shared.pack(folder, name, [archived_comparator[cases[0]]])
            plots.append(
                dict(
                    key="one",
                    label="Standalone majority",
                    file=name,
                    value=method,
                    match=["native_sha256", "catalog_sha256", "tile"],
                )
            )
        save_json(
            folder / "figure-lock.json",
            dict(
                cases=cases,
                files=files,
                original_prediction_sha256=lock["files"][f"{CANDIDATE}.jsonl.gz"],
            ),
        )
        title = {
            "fresh-synthetic": "Orbit-split halo at two fresh sites",
            "archived-roof": "Orbit-split halo on two known roof errors",
            "archived-majority": "Halo and majority on the archived near omission",
        }[scope]
        seen = {q["condition"] for q in queries}
        spec = dict(
            id=f"native_halo_orbit_consensus-{scope}",
            method=CANDIDATE,
            scope="transfer",
            title=title,
            caption="Independent assigned-orbit halves within an offer-centered halo.",
            cases=cases,
            queries="figure-queries.json",
            seal="figure-lock.json",
            series=plots,
            condition_labels={k: v for k, v in CONDITIONS.items() if k in seen},
        )
        write(
            folder / "figures.json",
            json.dumps(dict(version=1, charts=[spec]), indent=2).encode() + b"\n",
        )


def score(output, work):
    lock = phase._read(output / "prediction-lock.json")
    trial.clock.base.secant_full._verify_files(output, lock["files"])
    plan = phase._read(output / "roster.json")
    oracle = work / "evaluator.json"
    if phase.digest(oracle) != plan["evaluator_sha256"]:
        raise ValueError("blinded geography changed after prediction")
    write(output / "evaluator.json", oracle.read_bytes())
    labels = phase._read(oracle)["labels"]
    records = read_predictions(output / f"{CANDIDATE}.jsonl.gz")
    if not set(records) == set(labels) == set(lock["cases"]):
        raise ValueError("halo predictions differ from calibrated query roster")
    rows = score_rows(records, labels)
    previous, archived_majority = related(records, labels)
    shared.csv_file(output / "scores.csv", rows)
    save_json(
        output / "summary.json",
        dict(
            groups=summarize(rows),
            earlier_diagnostics=previous,
            elapsed_s=lock["elapsed_s"],
            optional_majority_blocker=plan["optional_majority_blocker"],
        ),
    )
    manifest(output, records, labels, archived_majority, lock)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, default=trial.REPORT)
    cli.add_argument("--work", type=Path, default=trial.WORK)
    args = cli.parse_args()
    score(args.output, args.work)


if __name__ == "__main__":
    main()
