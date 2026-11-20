"""Score captured oracle replays separately from fresh paired receiver runs."""

import argparse
from collections import Counter
from pathlib import Path

from ..__main__ import save_json
from ..scoring import ARMS, distance_km, distribution, thresholds, validate_result
from . import late_routing_archive as captured
from . import late_routing_bypass as negative
from . import late_routing_sources as measured
from . import late_routing_trial as trial
from .full_receiver_comparison import read, require_fields, roster_matches, seal, sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .pruned_finish_eval import historical_controls
from .short_receiver_figures import _frozen_roof

ARCHIVE_METHOD = "late_curvature_archive"
CAVITY = "late_curvature_cavity"
ORACLE = "late_curvature_oracle"
DIAGNOSTIC = {"DS26-0066", "DS26-0287"}
STAGE_NAMES = ("residual_screen", "addition", "ranking", "admission", "final")
MATCH = ("native_sha256", "catalog_sha256", "tile")


def archive_rows(feature, outcome, truth, reference):
    run = feature["route"]["run"]
    binding = {k: feature[k] for k in ("id", *MATCH, "request_sha256", "archive_sha256")}
    arms = {CAVITY: {}, ORACLE: {}, ARCHIVE_METHOD: {}}
    scores = []
    for arm, independent in reference.items():
        stages = outcome["stages"][arm]
        if stages["final"]["latlon"] != independent["latlon"]:
            raise ValueError("individual oracle endpoint differs from the frozen baseline")
        for method, stage in (
            (CAVITY, "cavity"), (ORACLE, "final"), (ARCHIVE_METHOD, "final" if run else "cavity")
        ):
            row = stages[stage]
            arms[method][arm] = dict(latlon=row["latlon"], rf_rms_hz=row["rf_rms_hz"])
        scores.append(dict(
            id=feature["id"],
            split="diagnosis" if feature["id"] in DIAGNOSTIC else "independent",
            arm=arm,
            dispatch=run,
            addition_moved=stages["cavity"]["x"] != stages["incumbent"]["x"],
            reassociation_moved=stages["incumbent"]["x"] != stages["final"]["x"],
            released_target_count=len(feature["samples"]),
            qualified_targets=sum(row["qualified"] for row in feature["route"]["targets"]),
            movement_km=distance_km(stages["cavity"]["latlon"], stages["final"]["latlon"]),
            **{f"{m}_km": distance_km(r[arm]["latlon"], truth) for m, r in arms.items()},
            **{f"{m}_hz": r[arm]["rf_rms_hz"] for m, r in arms.items()},
        ))
    outputs = [
        dict(
            binding,
            method=method,
            result=dict(
                status="ok",
                arms=value,
                metrics=dict(dispatch=run),
                boundary={
                    CAVITY: "Original archived cavity endpoint",
                    ORACLE: "Original archived full-late oracle endpoint",
                    ARCHIVE_METHOD: "Offline selection of authenticated archived endpoints",
                }[method],
            ),
        )
        for method, value in arms.items()
    ]
    return scores, outputs


def summarize(scores, raw, previous):
    out = {}
    for key, keep in (("all", set(raw)), ("independent", set(raw) - DIAGNOSTIC)):
        cases = [raw[i] for i in sorted(keep)]
        selected = {i for i in keep if raw[i]["route"]["run"]}
        skipped = keep - selected
        panel = dict(
            total=len(keep),
            dispatched=sorted(selected),
            bypassed=sorted(skipped),
            old_rf_only_reassociation_bypasses=sum(
                not previous[i]["preflight"]["run"] for i in keep
            ),
            invalid=sorted({r["id"] for r in cases if r["route"].get("reason")}),
            guard_cpu_s=distribution(r["route"]["cpu_s"] for r in cases),
            summed_original_stage_wall_s={
                stage: dict(
                    total=sum(raw[i]["original_stage_wall_s"][stage] for i in keep),
                    bypassed=sum(raw[i]["original_stage_wall_s"][stage] for i in skipped),
                )
                for stage in STAGE_NAMES
            },
            arms={},
        )
        for arm in ARMS:
            rows = [r for r in scores if r["id"] in keep and r["arm"] == arm]
            recoveries = {
                r["id"] for r in rows if r["addition_moved"] or r["reassociation_moved"]
            }
            benefits = {r["id"] for r in rows if r[CAVITY + "_km"] - r[ORACLE + "_km"] >= 0.1}
            panel["arms"][arm] = dict(
                changed=sorted(recoveries),
                changed_bypassed=sorted(recoveries & skipped),
                geographic_benefit_100m=sorted(benefits),
                geographic_benefit_lost=sorted(benefits & skipped),
                within_5k_loss=sorted({
                    r["id"] for r in rows if r[ORACLE + "_km"] <= 5 < r[ARCHIVE_METHOD + "_km"]
                }),
                methods={
                    method: dict(
                        geography_km=distribution(r[method + "_km"] for r in rows),
                        within_km=thresholds([r[method + "_km"] for r in rows]),
                        conditional_rms_hz=distribution(r[method + "_hz"] for r in rows),
                    )
                    for method in (CAVITY, ORACLE, ARCHIVE_METHOD)
                },
            )
        out[key] = panel
    return out


def plot(
    out, *, ident, method, control, title, caption, candidates, cases, evidence, scope, match=MATCH
):
    file = f"{ident}-positions.jsonl.gz"
    receipt = f"{ident}-figure-lock.json"
    pack(out / file, candidates)
    save_json(
        out / receipt,
        dict(cases=cases, files={name: sha(out / name) for name in (file, *evidence)}),
    )
    return dict(
        id=ident, method=method, title=title, caption=caption, seal=receipt,
        scope="roof", cases=scope, provenance=list(evidence),
        series=[
            dict(key="one", file=file, label="Curvature routing", value=method),
            dict(
                key="stock", file=file, label="Matched control",
                match=list(match), value=control,
            ),
        ],
    )


def archive(out, refs):
    lock = seal(out, captured.LOCK, (captured.BLIND,))
    measured.measured_sources(out)
    require_fields(lock, dict(
        run_lock_sha256=sha(out / "run-lock.json"),
        original_evidence_lock_sha256=sha(captured.PREVIOUS / "roof-lock.json"),
    ))
    seal(captured.PREVIOUS, "roof-lock.json", ("predecision.json.gz", "outcomes.json.gz"))
    raw, original, previous = (
        {row["id"]: row for row in captured.load(path)}
        for path in (
            out / captured.BLIND,
            captured.PREVIOUS / "outcomes.json.gz",
            captured.PREVIOUS / "predecision.json.gz",
        )
    )
    for rows in (raw, original, previous):
        roster_matches(rows, refs, "captured curvature replay")
    scores, candidates = [], []
    for ident, ref in refs.items():
        need = original[ident]["original_eligibility"]["residual_targets"]
        if len(raw[ident]["samples"]) != need:
            raise ValueError(f"{ident} residual evidence differs from stock target count")
        require_fields(raw[ident], {k: previous[ident][k] for k in (*MATCH, "request_sha256")})
        records, outputs = archive_rows(raw[ident], original[ident], ref["truth"], {
            arm: ref["reference"]["baseline"][arm] for arm in ARMS
        })
        scores.extend(records)
        candidates.extend(outputs)
    csv_file(out / "archive-scores.csv", scores)
    save_json(out / "archive-summary.json", summarize(scores, raw, previous))
    return plot(
        out, ident="late-curvature-roof135", method=ARCHIVE_METHOD, control=CAVITY,
        title="Held Doppler curvature and late v5 recovery on 135 recordings",
        caption=(
            "Archived original v5 checkpoints only. Curvature computed before late screening "
            "selects the saved full-late or cavity position. "
            "Fresh receiver measurements are separate."
        ),
        candidates=candidates, cases=sorted(refs), scope="roof135",
        evidence=("archive-scores.csv", "archive-summary.json", captured.LOCK),
    )


def live(out, refs, scratch):
    scheduled = read(out / "run-lock.json")
    controls = historical_controls({
        i: trial.execution_binding(item, trial._case(item))
        for i, item in trial.frozen_inputs().items()
        if i in {"DS26-0066", "DS26-0287", "DS26-0002", "DS29-0082"}
    })
    jobs = {i: (fields, "run-lock.json") for i, fields in scheduled["inputs"].items()}
    if (out / negative.LOCK).is_file():
        extra = read(out / negative.LOCK)
        if extra != negative.plan():
            raise ValueError("supplemental bypass selection differs from its predecision seal")
        ident = extra["id"]
        if all((scratch / f"{ident}-{meth}.json").is_file() for meth in negative.PINS):
            jobs[ident] = (extra["input"], negative.LOCK)
    rows, scores, stats, receipts = [], [], {}, {}
    for ident, (fields, source_lock) in jobs.items():
        candidate = read(scratch / f"{ident}-{trial.METHOD}.json")
        control = controls.get(ident) or read(scratch / f"{ident}-{trial.STOCK}.json")
        for source, method in ((candidate, trial.METHOD), (control, trial.STOCK)):
            require_fields(source, dict(fields, method=method))
            if method == trial.METHOD or ident not in DIAGNOSTIC:
                require_fields(source, {"source_lock_sha256": sha(out / source_lock)})
                name = f"{ident}-{method}.json"
                receipts[name] = sha(scratch / name)
            validate_result(source["result"])
            rows.append(source)
        trial_result, stock_result = candidate["result"], control["result"]
        candidate_metrics = trial_result["metrics"]
        stock_metrics = stock_result["metrics"]
        stats[ident] = dict(
            candidate_status=trial_result["status"],
            aligned_status=stock_result["status"],
            candidate_guard=candidate_metrics.get("late_curvature"),
            candidate_addition=candidate_metrics.get("addition_status"),
            stock_addition=stock_metrics.get("addition_status"),
            candidate_reassociation=candidate_metrics.get("reassociation_selected"),
            stock_reassociation=stock_metrics.get("reassociation_selected"),
            same_core_fresh_pair=ident not in DIAGNOSTIC and source_lock == "run-lock.json",
            control_origin=(
                "sealed aligned control" if ident in DIAGNOSTIC else
                "fresh same-core pair" if source_lock == "run-lock.json" else
                "fresh parallel different-core pair"
            ),
            candidate_worker_wall_s=candidate["worker_wall_s"],
            stock_worker_wall_s=control["worker_wall_s"],
            candidate_worker_cpu_s=candidate["worker_cpu_s"],
            stock_worker_cpu_s=control.get("worker_cpu_s"),
            candidate_stage_wall_s=candidate_metrics.get("stage_s"),
            stock_stage_wall_s=stock_metrics.get("stage_s"),
        )
        for arm in ARMS:
            scored = {"id": ident, "arm": arm}
            for label, row in (("candidate", candidate), ("aligned", control)):
                result = row["result"]
                point = result["arms"][arm]["latlon"]
                scored[f"{label}_error_km"] = distance_km(point, refs[ident]["truth"])
                scored[f"{label}_conditional_rms_hz"] = result["metrics"].get(
                    f"{arm}_conditional_rms_hz"
                )
            scores.append(scored)
    save_json(out / "live-summary.json", dict(
        cases=stats, statuses=Counter(r["candidate_status"] for r in stats.values())
    ))
    save_json(out / "live-worker-lock.json", dict(
        cases=sorted(jobs),
        scratch_workers_sha256=receipts,
        source_locks={lock: sha(out / lock) for _, lock in jobs.values()},
        aligned_control_files={
            key: sha(trial.SCREEN / "armijo-finish/aligned" / key)
            for key in ("prediction-lock.json", "positions.jsonl.gz", "matched-requests.json")
        },
    ))
    csv_file(out / "live-scores.csv", scores)
    return plot(
        out, ident="late-curvature-live", method=trial.METHOD, control=trial.STOCK,
        title="Fresh stored-native receivers with held Doppler curvature routing",
        caption=(
            "Two diagnostic and two hash-drawn confirmation cases with same-request controls. "
            "Fresh confirmation controls and sealed aligned diagnostic controls use both "
            "calibration arms on the original roof tile. Any supplemental bypass check "
            "is identified separately in the measurement receipts."
        ),
        candidates=rows, cases=sorted(jobs), scope="sealed",
        evidence=("live-scores.csv", "live-summary.json", "live-worker-lock.json", "run-lock.json"),
        match=(*MATCH, "input_sha256", "scientific_request_sha256"),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path)
    args = parser.parse_args()
    refs, _ = _frozen_roof()
    plots = [archive(trial.REPORT, refs)]
    if args.scratch:
        plots.append(live(trial.REPORT, refs, args.scratch))
    save_json(trial.REPORT / "figures.json", dict(version=1, charts=plots))
