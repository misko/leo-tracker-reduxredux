"""Score and plot fresh same-Graph shared, soft and exact receiver results."""

import argparse
from collections import Counter
from pathlib import Path

from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, distribution, thresholds, validate_result
from ..variants import shared_orbit_fit
from . import native_joint_full_results as shared
from . import shared_orbit_fit_trial as trial

phase = trial.base.phase
FILE = "paired-positions.jsonl.gz"
IDENTITY = (
    "input_sha256", "native_sha256", "catalog_sha256", "observation_sha256", "tile", "counts",
)


def references(plan):
    sources = (
        (trial.prior.REPORT, plan["prior_soft_sha256"]),
        (trial.base.panel.REPORT, plan["native_joint_lock_sha256"]),
    )
    for folder, expected in sources:
        path = folder / "prediction-lock.json"
        if phase.digest(path) != expected:
            raise ValueError("earlier control lock changed")
        trial.base.base.secant_full._verify_files(folder, phase._read(path)["files"])
        yield read_predictions(folder / shared.PREDICTIONS)


def matching(rows, plan):
    soft, joint = references(plan)
    records = {method: {} for method in trial.METHODS}
    cohort = {i: c for c, ids in plan["cohorts"].items() for i in ids}
    checks = Counter()
    for ident, row in rows.items():
        variants = row.get("variants") or {
            method: dict(result=row["result"], timing={}) for method in trial.METHODS
        }
        if set(variants) != set(trial.METHODS):
            raise ValueError("incomplete matched backend records")
        for method, measured in variants.items():
            result = measured["result"]
            validate_result(result)
            older = soft if method == trial.METHODS[1] else joint if method == trial.EXACT else {}
            if ident in older and "variants" in row:
                old = older[ident]
                if any(row[k] != old[k] for k in IDENTITY):
                    raise ValueError(f"{ident} does not reproduce the same canonical native Graph")
                if any(result[k] != old["result"][k] for k in ("status", "reason", "arms")):
                    raise ValueError(f"{ident} changed the independently sealed {method} result")
                checks[method] += 1
            metadata = {k: v for k, v in row.items() if k not in ("result", "variants")}
            records[method][ident] = dict(
                metadata, method=method, result=result, backend=measured["timing"],
                study_cohort=cohort[ident],
            )
    return records, dict(checks)


def score_rows(records, plan):
    rows, queries = [], []
    for method, group in records.items():
        cases, offers = shared.matched_score_rows(group, plan, solver_stage="compared_backends")
        if not queries:
            queries = offers
        for row in cases:
            raw = group[row["id"]]
            metrics = raw["result"]["metrics"]
            held = metrics.get("held_by_arm", {}).get(row["arm"], {})
            row.update(
                method=method, study_cohort=raw["study_cohort"],
                held_rf_rms_hz=held.get("rf_rms_hz"),
                naturally_unseen_orbits=held.get("naturally_unseen_orbits"),
                shared_phase_parameters=metrics.get("shared_phase_parameters"),
                backend_wall_s=raw["backend"].get("wall_s"),
                backend_cpu_s=raw["backend"].get("cpu_s"),
            )
        rows.extend(cases)
    return rows, queries


def summary(rows):
    entries = []
    keyed = {(r["id"], r["method"], r["arm"]): r for r in rows}
    for cohort in sorted({r["study_cohort"] for r in rows}):
        for arm in ARMS:
            for method in trial.METHODS:
                group = [
                    r for r in rows if r["study_cohort"] == cohort
                    and r["arm"] == arm and r["method"] == method
                ]
                records = dict(
                    cohort=cohort, arm=arm, method=method, scheduled=len(group),
                    status=dict(Counter(r["status"] for r in group)),
                    withheld_reasons=dict(Counter(
                        r["reason"] for r in group if r["status"] == "withheld"
                    )),
                    within_km=thresholds([r["error_km"] for r in group]),
                    sources_by_metric={k: distribution(r[k] for r in group) for k in (
                        "error_km", "forced_error_km", "conditional_rms_hz", "held_rf_rms_hz",
                        "held_score", "backend_wall_s", "backend_cpu_s", "peak_rss_kib",
                        "naturally_unseen_orbits", "shared_phase_parameters",
                        "baseline_error_km",
                    )},
                )
                if method == trial.METHODS[0]:
                    pairs = {
                        control: [(r, keyed[r["id"], control, arm]) for r in group]
                        for control in trial.METHODS[1:]
                    }
                    records["paired_against"] = {
                        name: phase._pair_summary([
                            (a["error_km"], b["error_km"]) for a, b in pair
                            if a["error_km"] is not None and b["error_km"] is not None
                        ]) for name, pair in pairs.items()
                    }
                entries.append(records)
    return entries


def figures(output, groups, queries, digest, plan_sha):
    descriptors = []
    for cohort, ids in groups.items():
        omitted = cohort.endswith("wrong")
        keys = ("candidate", "stock", "one") if omitted else ("one", "stock", "one_native_factors")
        captions = ("Shared satellite phase", "Separate track phases", "Exact joint receiver")
        series = [
            dict(key=key, label=text, file=FILE, value=method, where=dict(study_cohort=cohort))
            for key, text, method in zip(keys, captions, trial.METHODS, strict=True)
        ]
        for item in series[1:]:
            item["match"] = ["input_sha256", "native_sha256", "catalog_sha256"]
        title = cohort.replace("_", " ")
        seal = f"{cohort}-figure-lock.json"
        files = {FILE: digest}
        descriptor = dict(
            id=f"native_shared_orbit_fit-{cohort.replace('_', '-')}",
            method=shared_orbit_fit.METHOD, scope="transfer" if omitted else "roof", cases=ids,
            title=f"Shared satellite timing on the {title} offers",
            caption="Three causal anonymous receivers share a fresh native Graph. Forced "
            "coordinates are diagnostic.", seal=seal, series=series,
            source_lock=dict(file="plan.json", digest_key="plan_sha256"),
        )
        if omitted:
            query_file = f"{cohort}-queries.json"
            save_json(output / query_file, dict(queries=[q for q in queries if q["id"] in ids]))
            files[query_file] = phase.digest(output / query_file)
            descriptor["queries"] = query_file
            for item, name in zip(series, captions, strict=True):
                item["forced_label"] = f"{name} forced diagnostic"
        save_json(output / seal, dict(cases=ids, files=files, plan_sha256=plan_sha))
        descriptors.append(descriptor)
    save_json(output / "figures.json", dict(version=1, charts=descriptors))


def score(work, bundle, output):
    shared.seal(
        work, bundle, output, prepare=trial.prepare,
        method=shared_orbit_fit.METHOD, fail=trial.base.failed,
    )
    lock = phase._read(output / "prediction-lock.json")
    plan = phase._read(output / "plan.json")
    candidate = read_predictions(output / shared.PREDICTIONS)
    records, checks = matching(candidate, plan)
    rows, queries = score_rows(records, plan)
    shared.csv_file(output / "scores.csv", rows)
    positions = [row for group in records.values() for row in group.values()]
    digest = shared.pack(output, FILE, positions)
    save_json(output / "summary.json", dict(
        replay=lock["run"], independently_reproduced=checks, comparisons=summary(rows),
        c_ablation={m: shared.ablation([r for r in rows if r["method"] == m]) for m in records},
        paired_sha256=digest,
    ))
    figures(output, plan["cohorts"], queries, digest, lock["files"]["plan.json"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=trial.WORK)
    parser.add_argument("--bundle", type=Path, default=trial.base.base.BUNDLE)
    parser.add_argument("--output", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    score(args.work, args.bundle, args.output)
