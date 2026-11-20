"""Score the sealed convergence policy against fresh and archived five-round fits."""

from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution
from . import stable_phase_trial as trial
from .prefix_figures import csv_file


def score(root=trial.REPORT):
    lock = trial.base._read(root / "prediction-lock.json")
    trial.secant_full._verify_files(root, lock["files"])
    groups = {m: read_predictions(root / (m + ".jsonl.gz")) for m in (trial.METHOD, trial.STOCK)}
    refs = {r["id"]: r for r in trial.verified.roster()}
    values, costs = [], []
    for ident in lock["cases"]:
        after, before = (groups[m][ident] for m in (trial.METHOD, trial.STOCK))
        if any(
            after[k] != before[k]
            for k in ("input_sha256", "native_sha256", "catalog_sha256", "tile")
        ):
            raise ValueError("phase control changed scientific input")
        a, b = after["result"], before["result"]
        cohort = "timing" if before["qualification"] == "fresh" else "confirmation"
        for arm in ARMS:
            p, q = a["arms"][arm], b["arms"][arm]
            ref = refs[ident]
            delta = distance_km(p["latlon"], q["latlon"])
            rms = p.get("rf_rms_hz")
            stock_rms = q.get("rf_rms_hz")
            delta_hz = rms - stock_rms if rms is not None and stock_rms is not None else None
            values.append(
                dict(
                    id=ident,
                    cohort=cohort,
                    arm=arm,
                    candidate_status=a["status"],
                    control_status=b["status"],
                    error_km=distance_km(p["latlon"], ref["truth"]),
                    control_error_km=distance_km(q["latlon"], ref["truth"]),
                    endpoint_delta_km=delta,
                    rf_rms_hz=rms,
                    control_rf_rms_hz=stock_rms,
                    delta_rf_rms_hz=delta_hz,
                    numerical_pass=(
                        a["status"] == b["status"] == "ok"
                        and delta is not None
                        and delta <= 0.01
                        and delta_hz is not None
                        and abs(delta_hz) < 0.1
                    ),
                    **{role + "_km": ref["reference"][role][arm]["error_km"] for role in ROLES},
                )
            )
        am, bm = a["metrics"], b["metrics"]
        rounds = am.get("phase_termination", [])
        fresh = cohort == "timing"
        costs.append(
            dict(
                id=ident,
                cohort=cohort,
                new_status=a["status"],
                old_status=b["status"],
                full_cpu_s=after["resources"]["cpu_s"],
                control_cpu_s=before["resources"]["cpu_s"] if fresh else None,
                full_wall_s=after["worker_wall_s"],
                control_wall_s=before["worker_wall_s"] if fresh else None,
                optimized_rounds=sum(r["performed"] for r in rounds),
                requested_rounds=sum(r["requested"] for r in rounds),
                saved_rounds=sum(r["requested"] - r["performed"] for r in rounds),
                objective_evaluations=am.get("position_optimizer", {}).get("evaluations"),
                control_objective_evaluations=bm.get("position_optimizer", {}).get("evaluations"),
                control_repeated_archive=before.get("archive_same_result") if fresh else None,
                **{
                    f"{prefix}{key}_wall_s": metrics.get("stage_s", {}).get(key)
                    for prefix, metrics in (("", am), ("control_", bm))
                    for key in (
                        "native_preparation",
                        "initial",
                        "conservative",
                        "family",
                        "signed",
                        "cavity",
                    )
                },
            )
        )
    csv_file(root / "scores.csv", values)
    csv_file(root / "resources.csv", costs)
    cohorts = {
        k: [r["id"] for r in costs if k == "all" or r["cohort"] == k]
        for k in ("all", "timing", "confirmation")
    }
    summary = {}
    charts = []
    for cohort, cases in cohorts.items():
        summary[cohort] = {}
        for arm in ARMS:
            subset = [r for r in values if r["id"] in cases and r["arm"] == arm]
            summary[cohort][arm] = dict(
                n=len(subset),
                published=sum(r["error_km"] is not None for r in subset),
                tolerance=sum(r["numerical_pass"] for r in subset),
                **{
                    k: distribution(r[k] for r in subset)
                    for k in (
                        "error_km",
                        "control_error_km",
                        "endpoint_delta_km",
                        "delta_rf_rms_hz",
                        "baseline_km",
                    )
                },
            )
        if cohort == "all":
            continue
        # Series selection uses the two exact cohort archives, each independently sealed.
        files = {
            "plan.json": lock["files"]["plan.json"],
            "prediction-lock.json": trial.base.digest(root / "prediction-lock.json"),
        }
        for m, records in groups.items():
            fname = f"{m}-{cohort}.jsonl.gz"
            files[fname] = trial.pack(root, fname, [records[i] for i in cases])
        seal = cohort + "-figure-lock.json"
        save_json(root / seal, dict(cases=cases, files=files))
        charts.append(
            dict(
                id="stable_phase-" + cohort,
                method=trial.METHOD,
                scope="roof",
                cases=cases,
                seal=seal,
                title="Stop settled orbital updates on "
                + (
                    "paired timing recordings"
                    if cohort == "timing"
                    else "four hash-selected roof recordings"
                ),
                caption=(
                    "The compact secant solver can end initial and salvage phase updates after "
                    "both orbit timing and position settle. Both methods receive the same stored "
                    "GLRT factors and causal TLEs."
                ),
                series=[
                    dict(
                        key="one",
                        label="Converged phase updates",
                        file=f"{trial.METHOD}-{cohort}.jsonl.gz",
                        value=trial.METHOD,
                    ),
                    dict(
                        key="stock",
                        label="Five phase updates",
                        file=f"{trial.STOCK}-{cohort}.jsonl.gz",
                        value=trial.STOCK,
                        match=["input_sha256", "native_sha256", "catalog_sha256", "tile"],
                    ),
                ],
            )
        )
    save_json(root / "summary.json", summary)
    save_json(root / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    score()
