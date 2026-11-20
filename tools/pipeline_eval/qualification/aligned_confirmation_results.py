"""Seal and score the prospective aligned Armijo finish confirmation."""

import argparse
import fcntl
from collections import Counter
from pathlib import Path

from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds, validate_result
from . import aligned_confirmation as trial
from . import armijo_finish_results as shared
from . import phase_confirmation as phase
from . import secant_full
from .prefix_figures import csv_file
from .secant_fit_trial import failed_result

METHOD = trial.METHOD
FILES = {
    METHOD: "positions.jsonl.gz",
    secant_full.METHOD: "secant-cavity-positions.jsonl.gz",
    secant_full.STOCK: "stock-cavity-positions.jsonl.gz",
}


def _candidate(work, plan, ident, cohort):
    binding = plan["bindings"][ident]
    path = work / ident / "prediction.json"
    if not path.is_file():
        started = path.parent.is_dir()
        return dict(
            binding,
            method=METHOD,
            cohort=cohort,
            worker_wall_s=None,
            result=failed_result(
                "failed" if started else "missing",
                "worker directory without terminal receipt"
                if started
                else "not attempted before replay cutoff",
            ),
        )
    row = phase._read(path)
    if (
        row["plan_sha256"] != phase.digest(work / "plan.json")
        or row["method"] != METHOD
        or row["cpu"] not in trial.CPUS
        or not 0 < row["deadline_s"] <= trial.CAP
        or any(row[k] != value for k, value in binding.items())
    ):
        raise ValueError(f"{ident} differs from the locked candidate run")
    result = row["result"]
    validate_result(result)
    proof = row.get("boundary_proof")
    if proof and proof["worker_request_sha256"] != phase.digest(
        path.parent / "position/request.json"
    ):
        raise ValueError(f"{ident} scientific worker request changed after inference")
    if result["status"] == "ok" and (
        result["boundary"] != trial.aligned.BOUNDARY
        or set(result["arms"]) != set(ARMS)
        or proof is None
        or not {"ordered_phase_seeds", "checked_residual_addition", "reassociation_selected"}
        <= result["metrics"].keys()
    ):
        raise ValueError(f"{ident} complete finish evidence is missing")
    return dict(row, cohort=cohort, original_run_sha256=phase.digest(path))


def _figure_spec(plan):
    charts = []
    for cohort in ("confirmation", "stress"):
        title = (
            "Aligned Armijo finish on 15 new roof recordings"
            if cohort == "confirmation"
            else "Aligned Armijo on four cavity stress cases"
        )
        caption = (
            "Eight hash-selected DS26 cases and seven unused DS29 cases with matched controls."
            if cohort == "confirmation"
            else "Four separate cases selected for known cavity loss or geographic displacement."
        )
        series = []
        for key, method, label in (
            ("one", METHOD, "Aligned Armijo complete finish"),
            ("all_visits", secant_full.METHOD, "Archived secant cavity"),
            ("stock", secant_full.STOCK, "Archived stock compact cavity"),
        ):
            entry = dict(
                key=key, label=label, file=FILES[method], value=method, where=dict(cohort=cohort)
            )
            if key != "one":
                entry["match"] = [
                    "input_sha256",
                    "native_sha256",
                    "catalog_sha256",
                    "frozen_request_sha256",
                ]
            series.append(entry)
        charts.append(
            dict(
                id=f"armijo_aligned_{cohort}",
                method=METHOD,
                scope="roof",
                title=title,
                caption=caption,
                cases=plan["cohorts"][cohort],
                seal=f"{cohort}-lock.json",
                series=series,
                source_lock=dict(file="source-lock.json", digest_key="source_lock_sha256"),
                provenance=["plan.json", "original-v5-inputs.json"],
            )
        )
    return dict(version=1, charts=charts)


def seal(work, output):
    with (work / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = phase._read(work / "plan.json")
        if plan != trial.prepare(phase.frozen_inputs(), trial.source_lock()):
            raise ValueError("frozen schedule or compute source changed")
        controls = {
            method: read_predictions(secant_full.REPORT / f"{method}.jsonl.gz")
            for method in (secant_full.METHOD, secant_full.STOCK)
        }
        rows = {method: [] for method in FILES}
        for cohort, cases in plan["cohorts"].items():
            for ident in cases:
                candidate = _candidate(work, plan, ident, cohort)
                rows[METHOD].append(candidate)
                for method, records in controls.items():
                    row = records[ident]
                    if any(row[k] != v for k, v in plan["bindings"][ident].items()):
                        raise ValueError(
                            f"{ident} archived {method} differs from the frozen request"
                        )
                    proof = candidate.get("boundary_proof")
                    if proof and proof["resolved_request_sha256"] != row["resolved_request_sha256"]:
                        raise ValueError(
                            f"{ident} archived {method} differs from the numerical request"
                        )
                    rows[method].append(dict(row, cohort=cohort))
        save_json(output / "plan.json", plan)
        save_json(output / "source-lock.json", plan["source"])
        original = phase._read(secant_full.REPORT / "original-v5-inputs.json")
        save_json(
            output / "original-v5-inputs.json", {ident: original[ident] for ident in plan["cases"]}
        )
        files = {name: shared.pack(output, name, rows[method]) for method, name in FILES.items()}
        files.update(
            {name: phase.digest(output / name) for name in ("plan.json", "original-v5-inputs.json")}
        )
        common = dict(files=files, source_lock_sha256=phase.digest(output / "source-lock.json"))
        run_path = work / "run-receipt.json"
        run = phase._read(run_path) if run_path.is_file() else None
        if run and run["wall_s"] > trial.WALL_CAP:
            raise ValueError("confirmation ran past the 20 minute limit")
        save_json(
            output / "prediction-lock.json", dict(common, cases=plan["cases"], supervisor=run)
        )
        for cohort, cases in plan["cohorts"].items():
            save_json(output / f"{cohort}-lock.json", dict(common, cases=cases))
        save_json(output / "figures.json", _figure_spec(plan))


def _fields(result, arm):
    endpoint = result.get("arms", {}).get(arm, {})
    metrics = result["metrics"]
    return dict(
        conditional_doppler_rms_hz=metrics.get(
            f"{arm}_conditional_rms_hz", endpoint.get("rf_rms_hz")
        ),
        objective=metrics.get(f"{arm}_frequency_score"),
        associated_observations=metrics.get(f"{arm}_associated_observations"),
    )


def _execution_fields(candidate, arm):
    metrics = candidate["result"]["metrics"]
    adoption = metrics.get("checked_residual_addition", {})
    seeds = metrics.get("ordered_phase_seeds", {})
    return dict(
        candidate_status=candidate["result"]["status"],
        candidate_reason=candidate["result"].get("reason"),
        worker_wall_s=candidate.get("worker_wall_s"),
        worker_cpu_s=candidate.get("worker_cpu_s"),
        child_peak_rss_kib=candidate.get("resources", {}).get("child_peak_rss_kib"),
        numerical_worker_peak_rss_kib=metrics.get("numerical_worker_peak_rss_kib"),
        alignment_corrections=len(seeds["aligned"]) if seeds else None,
        equal_length_remaps=seeds.get("equal_length"),
        checked_addition_status=adoption.get("status"),
        checked_addition_source=adoption.get("source"),
        added_points=adoption.get("added_points", {}).get(arm),
        addition_status=metrics.get("addition_status"),
        reassociation_admitted=metrics.get("reassociation_admitted"),
        reassociation_selected=metrics.get("reassociation_selected"),
    )


def score(output):
    lock = phase._read(output / "prediction-lock.json")
    secant_full._verify_files(output, lock["files"])
    if phase.digest(output / "source-lock.json") != lock["source_lock_sha256"]:
        raise ValueError("aligned code source differs from the prediction lock")
    plan = phase._read(output / "plan.json")
    records = {method: read_predictions(output / name) for method, name in FILES.items()}
    if any(rows.keys() != set(lock["cases"]) for rows in records.values()):
        raise ValueError("the sealed prediction/control roster differs")
    refs = {r["id"]: r for r in phase.projector_roof.roster()}
    originals = phase._read(output / "original-v5-inputs.json")
    rows = []
    for ident in plan["cases"]:
        ref = refs[ident]
        candidate = records[METHOD][ident]
        original = {}
        archive = phase.ARCHIVE if ident.startswith("DS26-") else phase.DS29
        for role in ROLES:
            receipt = archive / f"{ident}-r0" / f"{role}-execution.json"
            if phase.digest(receipt) != originals[ident][role]["execution_sha256"]:
                raise ValueError(f"{ident} {role} execution differs from its frozen binding")
            original[role] = phase._read(receipt)["worker"]["arms"]
        for arm in ARMS:
            point = candidate["result"].get("arms", {}).get(arm, {}).get("latlon")
            row = dict(
                recording=ident,
                dataset=ref["group"],
                cohort=candidate["cohort"],
                stress_class=next(
                    (name for name, ids in trial.STRESS.items() if ident in ids), None
                ),
                arm=arm,
                **_execution_fields(candidate, arm),
            )
            for method, by_id in records.items():
                result = by_id[ident]["result"]
                fit = result.get("arms", {}).get(arm, {})
                row[f"{method}_error_km"] = distance_km(fit.get("latlon"), ref["truth"])
                if method != METHOD:
                    row[f"{method}_aligned_displacement_km"] = distance_km(point, fit.get("latlon"))
                row.update({f"{method}_{k}": v for k, v in _fields(result, arm).items()})
            for role, arms in original.items():
                fit = arms[arm]
                original_point = fit["endpoint_latlon"]
                if (
                    delta := distance_km(original_point, ref["reference"][role][arm]["latlon"])
                ) is None or delta > 1e-6:
                    raise ValueError(
                        f"{ident} original role endpoint differs from the published reference"
                    )
                row[f"{role}_error_km"] = distance_km(original_point, ref["truth"])
                row[f"{role}_aligned_displacement_km"] = distance_km(point, original_point)
                row[f"{role}_published_rms_hz"] = fit.get("residual_rms_hz")
                row[f"{role}_objective"] = fit.get("frequency_score")
            rows.append(row)
    csv_file(output / "scores.csv", rows)
    save_json(output / "summary.json", _summaries(rows))


def _summaries(rows):
    groups, process = [], {}
    for cohort in ("confirmation", "stress"):
        both = [r for r in rows if r["cohort"] == cohort]
        once = [r for r in both if r["arm"] == ARMS[0]]
        process[cohort] = dict(
            status=dict(Counter(r["candidate_status"] for r in once)),
            additions=dict(Counter(r["checked_addition_status"] or "unreported" for r in once)),
            added_points={
                arm: sum(r["added_points"] or 0 for r in both if r["arm"] == arm) for arm in ARMS
            },
            selected_reassociations=[
                r["recording"] for r in once if r["reassociation_selected"] is not None
            ],
            corrected_recordings=[
                r["recording"] for r in once if (r["alignment_corrections"] or 0) > 0
            ],
            **{
                key: distribution(r[key] for r in once)
                for key in (
                    "worker_wall_s",
                    "worker_cpu_s",
                    "child_peak_rss_kib",
                    "numerical_worker_peak_rss_kib",
                )
            },
        )
        for dataset in ("all", "DS26", "DS29"):
            for arm in ARMS:
                matched = [r for r in both if r["arm"] == arm and dataset in ("all", r["dataset"])]
                if not matched:
                    continue
                for method in (*FILES, *ROLES):
                    errors = [r[f"{method}_error_km"] for r in matched]
                    paired = [
                        (r[f"{METHOD}_error_km"], e)
                        for r, e in zip(matched, errors, strict=True)
                        if r[f"{METHOD}_error_km"] is not None and e is not None
                    ]
                    groups.append(
                        dict(
                            cohort=cohort,
                            dataset=dataset,
                            arm=arm,
                            method=method,
                            scheduled=len(matched),
                            error_km=distribution(errors),
                            within_km=thresholds(errors),
                            conditional_doppler_rms_hz=distribution(
                                r.get(f"{method}_conditional_doppler_rms_hz") for r in matched
                            ),
                            original_publication_rms_hz=distribution(
                                r.get(f"{method}_published_rms_hz") for r in matched
                            ),
                            objective=distribution(r.get(f"{method}_objective") for r in matched),
                            aligned_displacement_km=distribution(
                                r.get(f"{method}_aligned_displacement_km") for r in matched
                            ),
                            paired_errors=phase._pair_summary(paired) if method != METHOD else None,
                        )
                    )
    return dict(groups=groups, process=process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("seal", "score"))
    parser.add_argument("--work", type=Path, default=trial.SCRATCH)
    parser.add_argument("--output", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    if args.command == "seal":
        seal(args.work, args.output)
    else:
        score(args.output)


if __name__ == "__main__":
    main()
