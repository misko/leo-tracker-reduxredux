"""Score the paired native filter replays after their predictions are sealed."""

import argparse
from pathlib import Path

from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution
from . import innovation_noise_trial as trial
from . import native_joint_full_results as original
from .native_joint_results import geodata
from .prefix_figures import csv_file
from .train_update_results import matched

phase = trial.phase


def examine(record, control, archived, ref, arm):
    truth = ref["truth"]
    candidate, stock = geodata(record, arm, truth), geodata(control, arm, truth)
    each = (record, control)
    positions = [r["result"]["arms"][arm] for r in each]
    a, b = positions
    both_ran = all(r["result"]["status"] in {"ok", "withheld"} for r in each)
    shift = distance_km(a.get("forced_latlon"), b.get("forced_latlon"))
    rms_delta = (
        abs(a["rf_rms_hz"] - b["rf_rms_hz"])
        if all(p.get("rf_rms_hz") is not None for p in positions)
        else None
    )
    missing_both = all(p.get("forced_latlon") is None for p in positions)
    return dict(
        id=record["id"],
        recording=record["recording"],
        dataset=record["recording"].split("-")[0],
        cohort=record["cohort"],
        arm=arm,
        **candidate,
        dense_error_km=stock["error_km"],
        dense_forced_error_km=stock["forced_error_km"],
        dense_rms_hz=stock["conditional_rms_hz"],
        endpoint_delta_km=shift,
        absolute_rms_delta_hz=rms_delta,
        same_decision=(candidate["status"], candidate["reason"])
        == (stock["status"], stock["reason"]),
        within_prespecified_tolerance=bool(
            both_ran
            and (candidate["status"], candidate["reason"]) == (stock["status"], stock["reason"])
            and (
                (
                    shift is not None
                    and shift <= 0.001
                    and rms_delta is not None
                    and rms_delta <= 0.1
                )
                or missing_both
            )
        ),
        dense_reproduces_archive=all(
            control["result"].get(k) == archived["result"].get(k)
            for k in ("arms", "status", "reason")
        ),
        **{
            f"{role}_error_km": ref.get("reference", {}).get(role, {}).get(arm, {}).get("error_km")
            for role in ROLES
        },
    )


def costs(record, control):
    def resource(row, *keys):
        for k in keys:
            row = (row or {}).get(k)
        return row

    def paired(*keys):
        return tuple(resource(row, *keys) for row in (record, control))

    out = dict(id=record["id"], cohort=record["cohort"])
    resources = {
        "full_cpu_s": ("worker", "cpu_s"),
        "full_wall_s": ("worker_wall_s",),
        "rss_kib": ("resident_peak_kib",),
        "backend_cpu_s": ("stages", "joint_backend", "cpu_s"),
        "observation_s": ("result", "metrics", "observation_s"),
        "shortlist_s": ("result", "metrics", "shortlist_s"),
        "fit_s": ("result", "metrics", "fit_s"),
    }
    for name, keys in resources.items():
        a, b = paired(*keys)
        out[name], out["dense_" + name] = a, b
        out["delta_" + name] = a - b if a is not None and b is not None else None
    metrics = record["result"]["metrics"]
    out.update(
        retained_points=metrics.get("unique_fit_points"),
        dense_filter_bytes=metrics.get("dense_noise_bytes"),
        filter_bytes=metrics.get("filter_noise_bytes"),
    )
    return out


def figures(root, records, lock, method, chart_id, label, title):
    specs = []
    parent_figure = phase._read(trial.panel.REPORT / "omitted-figure-lock.json")
    trial.base.secant_full._verify_files(trial.panel.REPORT, parent_figure["files"])
    queries = phase._read(trial.panel.REPORT / "omitted-queries.json")["queries"]
    for cohort in ("roof", "omitted"):
        roof = cohort == "roof"
        cases = [r["id"] for r in records.values() if r["cohort"] == cohort]
        s = dict(
            id=f"{chart_id}-{cohort}",
            method=method,
            scope="roof" if roof else "transfer",
            cases=cases,
            seal=cohort + "-figure-lock.json",
            title=f"{title} on roof recordings"
            if roof
            else f"{title} with the roof outside the offered region",
            caption=(
                "Both workers start from the same complete GLRT factors and use the same tracks, "
                "orbital catalogue, noise covariance and position gates."
            ),
            series=[
                dict(
                    key="one" if roof else "candidate",
                    label=label,
                    file=method + ".jsonl.gz",
                    value=method,
                    where=dict(cohort=cohort),
                ),
                dict(
                    key="stock",
                    label="Dense track covariance",
                    file=trial.base.METHOD + ".jsonl.gz",
                    value=trial.base.METHOD,
                    where=dict(cohort=cohort),
                    match=["input_sha256", "native_sha256", "catalog_sha256"],
                ),
            ],
        )
        files = dict(lock["files"])
        if not roof:
            s["queries"] = "omitted-queries.json"
            selected = [q for q in queries if q["id"] in cases]
            if len(selected) != len(cases):
                raise ValueError("unbound omitted offer in figure")
            save_json(root / s["queries"], dict(queries=selected))
            files[s["queries"]] = phase.digest(root / s["queries"])
        save_json(root / s["seal"], dict(cases=cases, files=files))
        specs.append(s)
    save_json(root / "figures.json", dict(version=1, charts=specs))


def score(
    root,
    *,
    method=trial.METHOD,
    chart_id="innovation_noise",
    label="Scalar noise filter",
    title="Scalar Doppler noise filter",
):
    root = Path(root)
    lock = phase._read(root / "prediction-lock.json")
    original_lock = phase._read(trial.panel.REPORT / "prediction-lock.json")
    if phase._read(root / "plan.json")["source"]["reference"] != phase.digest(
        trial.panel.REPORT / "prediction-lock.json"
    ):
        raise ValueError("different original joint control")
    for directory, seal in ((root, lock), (trial.panel.REPORT, original_lock)):
        trial.base.secant_full._verify_files(directory, seal["files"])
    candidate = read_predictions(root / (method + ".jsonl.gz"))
    dense = read_predictions(root / (trial.base.METHOD + ".jsonl.gz"))
    old = read_predictions(trial.panel.REPORT / original.PREDICTIONS)
    if set(candidate) != set(dense) or set(candidate) != set(lock["cases"]):
        raise ValueError("incomplete matched roster")
    refs = {
        r["id"]: r for panel in ("ds26-common127", "roof16") for r in phase.corpus.references(panel)
    }
    omitted_figure = phase._read(trial.panel.REPORT / "omitted-figure-lock.json")
    trial.base.secant_full._verify_files(trial.panel.REPORT, omitted_figure["files"])
    omitted = {
        q["id"]: q for q in phase._read(trial.panel.REPORT / "omitted-queries.json")["queries"]
    }
    rows, timings = [], []
    for ident in lock["cases"]:
        row, control, last = candidate[ident], dense[ident], old[ident]
        matched(row, control)
        matched(control, last)
        ref = refs[ident] if row["cohort"] == "roof" else omitted[ident]
        if (original.roi_margin(ref["truth"], row["tile"]) >= 0) != (row["cohort"] == "roof"):
            raise ValueError("offer disagrees with physical roof condition")
        rows.extend(examine(row, control, last, ref, arm) for arm in ARMS)
        timings.append(costs(row, control))
    csv_file(root / "scores.csv", rows)
    csv_file(root / "resources.csv", timings)
    summary = {}
    for cohort in ("roof", "omitted"):
        resource = [r for r in timings if r["cohort"] == cohort]
        summary[cohort] = dict(
            resources={
                k: distribution(r[k] for r in resource)
                for k in resource[0]
                if k not in {"id", "cohort"}
            }
        )
        for arm in ARMS:
            group = [r for r in rows if r["cohort"] == cohort and r["arm"] == arm]
            summary[cohort][arm] = dict(
                n=len(group),
                published=sum(r["error_km"] is not None for r in group),
                exact_decisions=sum(r["same_decision"] for r in group),
                tolerance_passes=sum(r["within_prespecified_tolerance"] for r in group),
                original_dense_repeats=sum(r["dense_reproduces_archive"] for r in group),
                **{
                    k: distribution(r[k] for r in group)
                    for k in (
                        "error_km",
                        "dense_error_km",
                        "forced_error_km",
                        "baseline_error_km",
                        "endpoint_delta_km",
                        "absolute_rms_delta_hz",
                        "conditional_rms_hz",
                    )
                },
            )
    summary["calibration"] = original.ablation(rows)
    save_json(root / "summary.json", summary)
    figures(root, candidate, lock, method, chart_id, label, title)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiled", action="store_true")
    if parser.parse_args().compiled:
        from . import innovation_native_trial as compiled

        score(
            compiled.REPORT,
            method=compiled.METHOD,
            chart_id="compiled_innovation",
            label="Compiled scalar filter",
            title="Compiled scalar Doppler noise filter",
        )
    else:
        score(trial.REPORT)
