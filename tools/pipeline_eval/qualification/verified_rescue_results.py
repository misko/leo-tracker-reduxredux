"""Schedule matched late-symbol rescue fits and render from their sealed predictions."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, ROLES
from . import support_cross_trial
from . import verified_rescue as study
from .full_held_scores import held_references
from .full_v5_check import _sha
from .margin_admission_results import fit
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file

REPORT = study.REPORT
CPUS = dict(zip(study.CASES, (8, 9, 10, 11), strict=True))
MATCH = ["tile", "mode", "paired_capture_sha256", "catalog_sha256", "original_request_sha256"]


def execution():
    return dict(
        cpu_by_recording=CPUS,
        methods=list(study.CONDITIONS),
        source={
            str(p.relative_to(ROOT)): _sha(p)
            for p in (
                Path(study.__file__),
                Path(study.verified_rescue_raw.__file__),
                Path(study.pilot_confirmation.__file__),
                Path(support_cross_trial.__file__),
                REPORT / "PROTOCOL.md",
            )
        },
        parent_pooled_position_lock=study.POOL_PIN,
        memory_bytes=whole_iq.MEMORY,
        swap_bytes=0,
        time_limit_s=support_cross_trial.LIMIT,
    )


def run(work):
    if whole_iq.read(REPORT / "execution-lock.json") != execution():
        raise ValueError("predeclared raw selection or scheduling changed")
    if (REPORT / "prediction-lock.json").exists():
        raise FileExistsError("the completed experiment already has a prediction receipt")
    plans = {}
    probes, timings = [], []
    for ident, cpu in CPUS.items():
        folder = work / ident
        source = whole_iq.read(folder / "prepared.json")
        for name in ("raw-plan", "witness", "measures", "costs"):
            field = name.replace("-", "_") + "_sha256"
            suffix = {"raw-plan": ".json", "witness": ".jsonl"}.get(name, ".jsonl.gz")
            whole_iq.checked(folder / (name + suffix), source[field])
        if any(_sha(ROOT / name) != v for name, v in source["source_sha256"].items()):
            raise ValueError("measurement code changed after the raw read")
        if tuple(r["condition"] for r in source["jobs"]) != study.CONDITIONS:
            raise ValueError("missing a matched selector")
        probes.extend(study.lines(folder / "measures.jsonl.gz"))
        timings.extend(study.lines(folder / "costs.jsonl.gz"))
        ordered = source["jobs"] if ident.startswith("DS26") else list(reversed(source["jobs"]))
        plans[ident] = dict(
            raw_receipt={k: v for k, v in source.items() if k != "jobs"},
            jobs=[dict(r, cpu=cpu) for r in ordered],
        )
    save_json(REPORT / "input-lock.json", plans)
    write(REPORT / "probes.jsonl.gz", compressed_rows(probes))
    write(REPORT / "verification-costs.jsonl.gz", compressed_rows(timings))

    def run_case(ident):
        rows = []
        for job in plans[ident]["jobs"]:
            result = support_cross_trial.service(work, job)
            row = work / ident / job["condition"]
            whole_iq.checked(row / "service.log", result["log_sha256"])
            save_json(row / "terminal.json", result)
            rows.append(result)
        return rows

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        completed = [r for rows in pool.map(run_case, CPUS) for r in rows]
    write(REPORT / "predictions.jsonl.gz", compressed_rows(completed))
    files = (
        "PROTOCOL.md",
        "execution-lock.json",
        "input-lock.json",
        "probes.jsonl.gz",
        "verification-costs.jsonl.gz",
        "predictions.jsonl.gz",
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(cases=list(CPUS), files={n: _sha(REPORT / n) for n in files}),
    )


def positions():
    receipt = whole_iq.read(REPORT / "prediction-lock.json")
    for name, digest in receipt["files"].items():
        whole_iq.checked(REPORT / name, digest)
    plan = whole_iq.read(REPORT / "input-lock.json")
    new = study.lines(REPORT / "predictions.jsonl.gz")
    jobs = {(r["id"], r["condition"]): r for s in plan.values() for r in s["jobs"]}
    if len(new) != len(jobs) or {(r["id"], r["condition"]) for r in new} != jobs.keys():
        raise ValueError("not every scheduled fit is represented")
    for r in new:
        if any(r[k] != v for k, v in jobs[r["id"], r["condition"]].items()):
            raise ValueError("prediction no longer matches its physical inputs")
        if r["terminal"] == "success":
            for edge in ("start", "end"):
                resource = r["position_resources"][edge]
                if (resource["memory.max"], resource["memory.swap.max"], resource["cpus"]) != (
                    whole_iq.MEMORY,
                    0,
                    [CPUS[r["id"]]],
                ):
                    raise ValueError("resource receipt differs from the scheduled service")
    pool = whole_iq.read(whole_iq.checked(study.FOUR / "pooled-figure-lock.json", study.POOL_PIN))
    name = "pooled-positions.jsonl.gz"
    parents = study.lines(whole_iq.checked(study.FOUR / name, pool["files"][name]))
    if {(r["id"], r["method"]) for r in parents} != {
        (ident, "diagnostic_whole_" + mode) for ident in CPUS for mode in ("stock", "fftw")
    } or len(parents) != 8:
        raise ValueError("missing a stock or unconditional parent")
    for r in parents:
        reference = jobs[r["id"], "verified"]
        donor = r["method"] == "diagnostic_whole_fftw"
        if r["native_sha256"] != reference[
            "donor_native_sha256" if donor else "stock_native_sha256"
        ] or any(r[k] != reference[k] for k in MATCH):
            raise ValueError("unpaired detector, tile, or causal catalogue")
    return new, parents


def publish():
    new, parents = positions()
    all_rows = [*parents, *new]
    write(REPORT / "positions.jsonl.gz", compressed_rows(all_rows))
    _, reference = held_references(None, study.CASES)
    ref = {r["id"]: r for r in reference}
    scores = []
    for r in all_rows:
        for arm in ARMS:
            result = fit(r, ref[r["id"]], arm)
            v5 = {k: ref[r["id"]]["reference"][k][arm]["error_km"] for k in ROLES}
            error = result["error_km"]
            scores.append(
                dict(
                    **result,
                    frequency_score=r["result"]["metrics"].get(arm + "_frequency_score"),
                    within_5pct=error is not None and error <= 1.05 * v5["baseline"],
                    within_10pct=error is not None and error <= 1.1 * v5["baseline"],
                    **{k + "_km": v for k, v in v5.items()},
                )
            )
    csv_file(REPORT / "scores.csv", scores)
    times = []
    for r in new:
        measured = r.get("position_resources") or {}
        end = measured.get("end", {})
        times.append(
            dict(
                id=r["id"],
                condition=r["condition"],
                cpu=r["cpu"],
                terminal=r["terminal"],
                stock_negative_gains=r["proposed"],
                appended=r["accepted"],
                cpu_s=measured.get("cpu_s"),
                wall_s=measured.get("wall_s"),
                external_wall_s=r["supervisor_wall_s"],
                peak_bytes=measured.get("peak_bytes"),
                final_swap_bytes=end.get("memory.swap.current"),
                oom_kills=end.get("memory.events.oom_kill"),
            )
        )
    csv_file(REPORT / "resources.csv", times)
    names = ("positions.jsonl.gz", "scores.csv", "prediction-lock.json", "resources.csv")
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=list(CPUS), files={n: _sha(REPORT / n) for n in names}),
    )
    charts = []
    for mode, title in (
        ("verified", "Verify newly detected pilots using later symbols"),
        ("count_control", "Add the same number of pilots in fixed hash order"),
    ):
        methods = (
            (
                "one",
                "late_symbol_rescue_" + mode,
                "Late-symbol rescue" if mode == "verified" else "Count-matched rescue",
            ),
            ("stock", "diagnostic_whole_stock", "Stock wide GLRT"),
            ("one_native_factors", "diagnostic_whole_fftw", "Unconditional timing hint"),
        )
        series = [
            dict(
                key=k,
                label=label,
                file="positions.jsonl.gz",
                value=m,
                match=MATCH,
                native_field="paired_capture_sha256",
            )
            for k, m, label in methods
        ]
        charts.append(
            dict(
                id="late-symbol-rescue-" + mode.replace("_", "-"),
                title=title,
                method="late_symbol_rescue_" + mode,
                scope="roof",
                seal="figure-lock.json",
                cases="sealed",
                series=series,
                provenance=list(names[1:]),
                caption="Four full-I/Q detector pairs on one roof, with the same compact solver "
                "and four capture-era v5 references. All scheduled positions are counted.",
            )
        )
    save_json(REPORT / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("lock", "run", "score"))
    parser.add_argument("--work", type=local_output)
    args = parser.parse_args()
    if args.action == "lock":
        plan = execution()
        target = REPORT / "execution-lock.json"
        if target.exists() and whole_iq.read(target) != plan:
            raise ValueError("existing source or resource plan differs")
        save_json(target, plan)
    elif args.action == "run":
        run(args.work)
    else:
        publish()
