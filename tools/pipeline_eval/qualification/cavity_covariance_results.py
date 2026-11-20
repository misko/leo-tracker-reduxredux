"""Seal actual full compact pairs and check every cavity nomination and restoration."""

import argparse
from pathlib import Path

from ..__main__ import local_output, save_json
from ..scoring import ARMS, distance_km
from . import cavity_covariance as trial
from . import screening_figures as figures
from .aligned_confirmation import _request_proof
from .native_lean_eval import _write_predictions
from .phase_confirmation import _read, digest
from .prefix_figures import csv_file

FILES = ("positions.jsonl.gz", "stock-positions.jsonl.gz")
BINDING = ("input_sha256", "native_sha256", "catalog_sha256", "scientific_request_sha256")


def stages(row):
    metrics = row["result"]["metrics"]
    measured = metrics.get("cavity_covariance_observer", {})
    coarse = measured.get("coarse", [])
    return dict(
        worker_s=row["worker_wall_s"],
        worker_cpu_s=row["worker_cpu_s"],
        worker_peak_rss_kib=metrics.get("worker_peak_rss_kib"),
        family_data_wall_s=sum(s["wall_s"] for s in measured.get("family_data", [])),
        family_data_cpu_s=sum(s["cpu_s"] for s in measured.get("family_data", [])),
        coarse_wall_s=sum(s["wall_s"] for s in coarse),
        coarse_cpu_s=sum(s["cpu_s"] for s in coarse),
        coarse_peak_rss_kib=max((s["rss_after_kib"]["VmHWM"] for s in coarse), default=None),
        nomination=measured.get("nomination_stage"),
        restoration=measured.get("restored_stage"),
    )


def equality(a, b):
    a, b = (row["result"] for row in (a, b))
    if any(r["status"] != "ok" for r in (a, b)):
        return dict(compared=False, statuses=[a["status"], b["status"]])
    ma, mb = (r["metrics"] for r in (a, b))
    x, y = (r["cavity_covariance_observer"] for r in (ma, mb))
    ranks = [[s["order_sha256"] for s in r["coarse"]] for r in (x, y)]
    aliases = [[s["aliases_sha256"] for s in r["coarse"]] for r in (x, y)]
    rms = ("frequency_score", "conditional_rms_hz", "associated_observations")
    finish = (
        "residual_targets",
        "addition_status",
        "reassociation_targets",
        "reassociation_admitted",
        "reassociation_selected",
    )
    candidates = [c for family in x["nominations"]["families"] for c in family["candidates"]]
    return dict(
        compared=True,
        families=len(ranks[0]),
        fine_candidates=len(candidates),
        per_source_residuals=sum(len(c["source"]) for c in candidates),
        rank_order_exact=ranks[0] == ranks[1],
        alias_exact=aliases[0] == aliases[1],
        fine_nominations_and_source_residuals_exact=x["nominations"] == y["nominations"],
        restored_trials_and_selection_exact=x["restored"] == y["restored"],
        complete_finish_exact=a["arms"] == b["arms"]
        and all(
            ma.get(k) == mb.get(k) for k in (*finish, *(f"{arm}_{r}" for arm in ARMS for r in rms))
        ),
        endpoint_shift_km={
            arm: distance_km(a["arms"][arm]["latlon"], b["arms"][arm]["latlon"]) for arm in ARMS
        },
        dense_rank_fallbacks=sum(m["dense_fallback"] for m in x["mode_space"]),
        max_family_points=max((m["points"] for m in x["mode_space"]), default=0),
        max_dense_covariance_bytes=max(
            (m["dense_covariance_bytes"] for m in x["mode_space"]), default=0
        ),
        max_radio_mode_array_bytes=max(
            (m["radio_mode_array_bytes"] for m in x["mode_space"]), default=0
        ),
    )


def publish(work, report, retries=()):
    report = local_output(report)
    plan = _read(work / "plan.json")
    if plan["source"] != trial.source_tokens() or plan["frozen"] != trial.frozen_hashes():
        raise ValueError("the measured compact sources differ from their pre-run hashes")
    cohorts = {"primary": plan["primary"], "confirmation": list(plan["optional"].values())}
    overrides, followup = {}, {}
    for folder in retries:
        repeat_plan = _read(folder / "plan.json")
        (receipt,) = folder.glob("DS*.json")
        measured = _read(receipt)
        ident, method = measured["id"], measured["method"]
        original = work / receipt.name
        if (
            ident in overrides
            or repeat_plan["source"] != plan["source"]
            or repeat_plan["bindings"][ident] != plan["bindings"][ident]
            or repeat_plan["order"][ident] != [method]
            or trial.sha(original.read_bytes()) != repeat_plan["preserved_initial_timeout_sha256"]
            or _read(original)["result"]["status"] != "timed_out"
        ):
            raise ValueError(f"repeat for {ident} must bind its original timed-out attempt")
        overrides[ident] = method, folder
        followup[ident] = repeat_plan
    if overrides:
        cohorts["repeat"] = list(overrides)
    by_method = {m: [] for m in trial.METHODS}
    stage_rows, scores, pairs, attempted = [], [], {}, {k: [] for k in cohorts}
    refs, _ = figures.shared._frozen_roof()
    for group, cases in cohorts.items():
        for ident in cases:
            sources = {
                method: overrides[ident][1]
                if group == "repeat" and method == overrides[ident][0]
                else work
                for method in trial.METHODS
            }
            paths = [sources[method] / f"{ident}-{method}.json" for method in trial.METHODS]
            if not any(p.exists() for p in paths):
                if group == "primary":
                    raise ValueError(f"the scheduled primary {ident} has no attempt receipt")
                continue
            if not all(p.exists() for p in paths):
                raise ValueError(f"the attempted pair {ident} is missing one status envelope")
            attempted[group].append(ident)
            seen = []
            original_case = trial._case(trial.frozen_inputs()[ident])
            for method, receipt in zip(trial.METHODS, paths, strict=True):
                row = _read(receipt)
                req = sources[method] / ident / method / "request.json"
                if req.exists():
                    binding = _request_proof(original_case, req)
                    row.update(binding)
                elif row["result"]["status"] == "ok":
                    raise ValueError(f"{ident} {method} has no measured request")
                else:
                    row["scientific_request_sha256"] = plan["bindings"][ident][
                        "scientific_request_sha256"
                    ]
                if any(row[k] != plan["bindings"][ident][k] for k in BINDING):
                    raise ValueError(f"{ident} {method} has unmatched observations or science")
                row["cohort"] = group
                seen.append(row)
                metrics = dict(row["result"]["metrics"])
                observer = metrics.pop("cavity_covariance_observer", {})
                stage = stages(row)
                stage_rows.append(
                    dict(
                        id=ident,
                        method=method,
                        cohort=group,
                        measured_leg="original" if sources[method] == work else "repeat",
                        status=row["result"]["status"],
                        cpu=row["cpu"],
                        scientific_request_sha256=row["scientific_request_sha256"],
                        stages=stage,
                        observer=observer,
                    )
                )
                by_method[method].append(dict(row, result=dict(row["result"], metrics=metrics)))
                for arm in ARMS:
                    point = row["result"]["arms"][arm]["latlon"]
                    scores.append(
                        dict(
                            id=ident,
                            method=method,
                            arm=arm,
                            cohort=group,
                            status=row["result"]["status"],
                            reason=row["result"].get("reason"),
                            position_error_km=distance_km(point, refs[ident]["truth"]),
                            conditional_rf_rms_hz=metrics.get(f"{arm}_conditional_rms_hz"),
                            worker_cpu_s=row["worker_cpu_s"],
                            worker_wall_s=row["worker_wall_s"],
                        )
                    )
            pairs[f"{ident}-repeat" if group == "repeat" else ident] = equality(*seen)
    save_json(report / "source-lock.json", dict(files=plan["source"], frozen=plan["frozen"]))
    save_json(report / "plan.json", plan)
    save_json(
        report / "summary.json",
        dict(
            primary=attempted["primary"],
            confirmation_planned=cohorts["confirmation"],
            confirmation_attempted=attempted["confirmation"],
            repeat_attempted=attempted.get("repeat", []),
            pairs=pairs,
        ),
    )
    csv_file(report / "scores.csv", scores)
    _write_predictions(report / "stage-receipts.jsonl.gz", stage_rows)
    for name, method in zip(FILES, trial.METHODS, strict=True):
        _write_predictions(report / name, by_method[method])
    files = {
        name: digest(report / name)
        for name in (
            *FILES,
            "source-lock.json",
            "plan.json",
            "summary.json",
            "scores.csv",
            "stage-receipts.jsonl.gz",
        )
    }
    if followup:
        save_json(report / "repeat-plans.json", followup)
        files["repeat-plans.json"] = digest(report / "repeat-plans.json")
    charts = []
    for group, cases in attempted.items():
        if not cases:
            continue
        name = f"{group}-figure-lock.json"
        save_json(report / name, dict(cases=cases, files=files))
        captions = {
            "primary": "Original schedule on two roof recordings, including the actual timeout.",
            "confirmation": "Original salt-selected follow-up, including its actual timeout.",
            "repeat": "Same-input repeats compared with the completed legs of the first schedule.",
        }
        test = dict(
            id=f"{trial.low.METHOD}-{group}",
            method=trial.low.METHOD,
            scope="roof",
            title="Low-rank cavity nomination in compact v5",
            caption=captions[group],
            cases=cases,
            seal=name,
            provenance=["summary.json", "stage-receipts.jsonl.gz", "source-lock.json"],
            series=[
                dict(
                    key=key,
                    label=label,
                    file=file,
                    value=method,
                    where=dict(cohort=group),
                    **({"match": BINDING} if key == "stock" else {}),
                )
                for key, label, file, method in zip(
                    ("one", "stock"),
                    ("Low-rank covariance", "Fresh compact v5"),
                    FILES,
                    trial.METHODS,
                    strict=True,
                )
            ],
        )
        figures._chart(report, test)
        charts.append(test)
    save_json(report / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=trial.REPORT)
    parser.add_argument("--retry", type=Path, action="append", default=[])
    args = parser.parse_args()
    publish(args.work, args.report, args.retry)
