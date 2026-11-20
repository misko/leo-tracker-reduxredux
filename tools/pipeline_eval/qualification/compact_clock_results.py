"""Verify and score the compact, full-smooth, and original receivers."""

import argparse
from collections import Counter
from pathlib import Path

from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, distribution, thresholds
from ..variants import compact_clock
from . import compact_clock_trial as trial
from . import native_clock_full_results as full

shared, phase = full.shared, full.phase
SMOOTH = "smooth-positions.jsonl.gz"
JOINT = "joint-positions.jsonl.gz"
PAIR_FIELDS = ("input_sha256", "native_sha256", "catalog_sha256", "tile")
OWNERS = ("training_ownership", "final_c0_ownership", "final_fitted_c_ownership")
MEASURES = (
    "error_km", "forced_error_km", "conditional_rms_hz", "held_rf_rms_hz", "held_score",
    "worker_wall_s", "worker_cpu_s", "backend_wall_s", "peak_rss_kib",
)


def verified(candidate, smooth, stock):
    if not (set(candidate) == set(smooth) == set(stock)):
        raise ValueError("native compact, smooth and stock rosters differ")
    matches = {}
    for ident, row in candidate.items():
        controls = smooth[ident], stock[ident]
        for control in controls:
            if any(row[k] != control[k] for k in (*PAIR_FIELDS, "recording", "cohort")):
                raise ValueError(f"{ident} received different native queries")
        if row["result"]["status"] not in ("ok", "withheld"):
            matches[ident] = False
            continue
        if any(
            row["observation_sha256"] != control.get("observation_sha256")
            or row["counts"] != control.get("counts") for control in controls
        ):
            raise ValueError(f"{ident} native factors, peaks or Graph evidence changed")
        a, b = (r["result"]["metrics"] for r in (row, controls[0]))
        if a.get("receiver_clock_coordinates") != 8 or a.get("static_hardware_coordinates") != 4:
            raise ValueError(f"{ident} did not run the compact clock")
        left, right = a.get("clock_fit", {}), b.get("clock_fit", {})
        for key in OWNERS:
            if left.get(key) != right.get(key):
                raise ValueError(f"{ident} changed the smooth baseline's {key}")
        matches[ident] = all(key in left for key in OWNERS)
    return matches


def _measures(record, arm, position, stage):
    result = shared.geodata(record, arm, position)
    metrics = record["result"]["metrics"]
    result["held_rf_rms_hz"] = metrics.get(
        "held_by_arm", {}
    ).get(arm, {}).get("held_rf_rms_hz")
    result["backend_wall_s"] = record.get("stages", {}).get(stage, {}).get("wall_s")
    return result


def augment(rows, candidate, smooth, stock, matches, truth):
    for row in rows:
        ident, arm = row["id"], row["arm"]
        point = truth[row["recording"]]
        new = _measures(candidate[ident], arm, point, "clock_backend")
        reference = _measures(smooth[ident], arm, point, "clock_backend")
        original = _measures(stock[ident], arm, point, "joint_backend")
        row.update(
            equal_fixed_support=matches[ident],
            held_rf_rms_hz=new["held_rf_rms_hz"],
            backend_wall_s=new["backend_wall_s"],
            smooth_status=reference["status"],
            stock_status=original["status"],
            **{f"smooth_{key}": reference[key] for key in MEASURES},
            **{f"stock_{key}": original[key] for key in MEASURES},
        )


def comparisons(rows):
    output = []
    for cohort in ("roof", "omitted"):
        for dataset in ("all", "DS26", "DS29"):
            for arm in ARMS:
                group = [
                    r for r in rows if r["cohort"] == cohort and r["arm"] == arm
                    and dataset in ("all", r["dataset"])
                ]
                if not group:
                    continue
                matches = [r for r in group if r["equal_fixed_support"]]
                controls = {}
                for side in ("smooth", "stock"):
                    paired = [
                        (r["error_km"], r[f"{side}_error_km"]) for r in matches
                        if r["error_km"] is not None and r[f"{side}_error_km"] is not None
                    ]
                    controls[side] = dict(
                        statuses=dict(Counter(r[f"{side}_status"] for r in group)),
                        within_km=thresholds([r[f"{side}_error_km"] for r in group]),
                        paired_accuracy=phase._pair_summary(paired),
                        publication_pairs=dict(Counter(
                            f"{r['status']}/{r[f'{side}_status']}" for r in group
                        )),
                        measures={k: distribution(r[f"{side}_{k}"] for r in group)
                                  for k in MEASURES},
                        compact_minus_control={
                            k: distribution(
                                r[k] - r[f"{side}_{k}"] for r in matches
                                if r[k] is not None and r[f"{side}_{k}"] is not None
                            ) for k in MEASURES
                        },
                    )
                output.append(dict(
                    cohort=cohort, dataset=dataset, arm=arm, scheduled=len(group),
                    equal_fixed_support=len(matches),
                    compact_measures={key: distribution(r[key] for r in group)
                                      for key in MEASURES},
                    **controls,
                ))
    return output


def figure(output, candidate, smooth_sha, joint_sha, queries, lock):
    specs = []
    for name in ("roof", "omitted"):
        omitted = name == "omitted"
        methods = (compact_clock.METHOD, trial.smooth.METHOD, shared.METHOD)
        cases = [ident for ident, r in candidate.items() if r["cohort"] == name]
        files = lock["files"] | {SMOOTH: smooth_sha, JOINT: joint_sha}
        keys = ("candidate", "stock", "one") if omitted else ("one", "stock", "all_visits")
        caption = (
            "Nine wrong offers. Published and forced diagnostic coordinates are labeled."
            if omitted else "Identical complete native packets, Graph, catalogues and fixed "
            "support for the compact and full smooth clock fits. Both use exact held prediction."
        )
        subject = "nine wrong offers" if omitted else "135 roof recordings"
        spec = dict(
            id=f"native_compact_clock-{name}", method=compact_clock.METHOD,
            title=f"Compact receiver clock on {subject}",
            caption=caption, cases=cases, scope="transfer" if omitted else "roof",
            seal=f"{name}-figure-lock.json",
            source_lock=dict(file="plan.json", digest_key="plan_sha256"),
            series=[
                dict(key=key, label=label, file=path, value=method, where=dict(cohort=name))
                for key, label, path, method in zip(
                    keys,
                    ("Compact receiver clock", "Full smooth receiver clock", "As-built joint"),
                    (shared.PREDICTIONS, SMOOTH, JOINT), methods, strict=True,
                )
            ],
        )
        pinned = list(PAIR_FIELDS)
        if all(candidate[ident].get("observation_sha256") for ident in cases):
            pinned.append("observation_sha256")
        for series in spec["series"][1:]:
            series["match"] = pinned
        if omitted:
            for series in spec["series"]:
                series["forced_label"] = f'{series["label"]} forced diagnostic'
            spec["queries"] = "omitted-queries.json"
            save_json(output / spec["queries"], dict(queries=queries))
            files[spec["queries"]] = phase.digest(output / spec["queries"])
        save_json(output / spec["seal"], dict(
            cases=cases, files=files, plan_sha256=lock["files"]["plan.json"],
        ))
        specs.append(spec)
    save_json(output / "figures.json", dict(version=1, charts=specs))


def score(work, bundle, output):
    shared.seal(
        work, bundle, output, prepare=trial.prepare, method=compact_clock.METHOD,
        fail=trial.smooth.failed,
    )
    lock = phase._read(output / "prediction-lock.json")
    plan = phase._read(output / "plan.json")
    cache = {}
    for name, folder, digest in (
        ("smooth", trial.smooth.REPORT, plan["smooth_panel_sha256"]),
        ("stock", trial.smooth.panel.REPORT, plan["native_joint_lock_sha256"]),
    ):
        receipt = folder / "prediction-lock.json"
        if phase.digest(receipt) != digest:
            raise ValueError(f"the archived {name} comparison changed")
        files = phase._read(receipt)["files"]
        trial.smooth.base.secant_full._verify_files(folder, files)
        cache[name] = read_predictions(folder / shared.PREDICTIONS)
    candidate = read_predictions(output / shared.PREDICTIONS)
    smooth, stock = cache.values()
    matches = verified(candidate, smooth, stock)
    rows, queries = shared.matched_score_rows(candidate, plan, solver_stage="clock_backend")
    truth = {
        r["id"]: r["truth"] for panel in ("ds26-common127", "roof16")
        for r in phase.corpus.references(panel)
    }
    augment(rows, candidate, smooth, stock, matches, truth)
    shared.csv_file(output / "scores.csv", rows)
    hold = {r["id"]: r["held_rf_rms_hz"] for r in rows if r["arm"] == "c0"}
    deltas = [
        r["held_rf_rms_hz"] - hold[r["id"]] for r in rows
        if r["cohort"] == "roof" and r["arm"] == "fitted_c" and r["held_rf_rms_hz"] is not None
        and hold[r["id"]] is not None
    ]
    save_json(output / "summary.json", dict(
        replay=lock["run"], groups=shared.summarize(rows), controls=comparisons(rows),
        c_ablation=shared.ablation(rows), held_c_ablation=distribution(deltas),
    ))
    smooth_sha = shared.pack(output, SMOOTH, smooth.values())
    joint_sha = shared.pack(output, JOINT, stock.values())
    figure(output, candidate, smooth_sha, joint_sha, queries, lock)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=trial.WORK)
    parser.add_argument("--bundle", type=Path, default=trial.smooth.base.BUNDLE)
    parser.add_argument("--output", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    score(args.work, args.bundle, args.output)
