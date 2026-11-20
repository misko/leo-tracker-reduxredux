"""Seal the wide-factor witness and fresh paired position measurements."""

import argparse
import gzip
from difflib import unified_diff
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import fit_basis
from . import fit_basis_trial as trial
from .cavity_pressure_results import scientific_payload
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

COMMON = trial.COMMON
FILES = {trial.STOCK: "stock-positions.jsonl.gz", trial.CANDIDATE: "positions.jsonl.gz"}
MATCH = ("native_sha256", "catalog_sha256", "input_sha256", "tile")


def wrap(path, target):
    write(target, gzip.compress(path.read_bytes(), mtime=0))
    return target.name


def validate_record(plan, planfile, folder, case, method):
    row = whole_iq.read(folder / "receipt.json")
    COMMON.require_fields(
        row,
        dict(
            case=case,
            method=method,
            cpu=trial.CASES[case],
            native_sha256=plan["cases"][case]["native_sha256"],
            plan_sha256=COMMON.sha(planfile),
            log_sha256=COMMON.sha(folder / "service.log"),
        ),
    )
    marks = row["marks"]
    if row["service_result"] == "success" and (not {"ready", "finish"} <= marks.keys()):
        raise ValueError("missing physical resource proof for a completed inference")
    for key in ("ready", "finish"):
        if key in marks:
            value = marks[key]
            if (
                value["memory.max"] != plan["memory"]
                or value["memory.swap.max"]
                or value["memory.swap.current"]
            ):
                raise ValueError("cgroup changed from the physical memory and swap cap")
    if "ready" in marks and marks["ready"]["cpu"] != trial.CASES[case]:
        raise ValueError("unregistered numerical processor")
    if row["wall_s"] > plan["limit_s"] + 10:
        raise ValueError("receipt exceeds the specified service bound")
    if row["result"] is not None:
        validate_result(row["result"])
    return row


def resources(row):
    marks = row["marks"]
    end = marks.get("finish", {})
    moments = marks.get("statistics", {})
    kernel = row["kernel"]
    peak, cpu = (kernel.get(name, "") for name in ("MemoryPeak", "CPUUsageNSec"))
    calls, timings = (moments.get(key, {}) for key in ("calls", "process_cpu_s"))
    return dict(
        case=row["case"],
        method=row["method"],
        status=row["result"]["status"],
        cpu=row["cpu"],
        wall_s=row["wall_s"],
        process_cpu_s=end.get("process_cpu_s"),
        terminal_cgroup_cpu_s=int(cpu) / 1e9 if cpu.isdecimal() else None,
        peak_charge_bytes=end.get("memory.peak", int(peak) if peak.isdecimal() else None),
        worker_peak_rss_kib=end.get("rss_kib"),
        statistics_calls=calls.get("statistics", 0),
        augment_calls=calls.get("augment_phase_statistics", 0),
        statistics_cpu_s=timings.get("statistics"),
        augment_cpu_s=timings.get("augment_phase_statistics"),
        total_moments_cpu_s=sum(timings.values()) if timings else None,
        compact_projections=row["result"]["metrics"].get("compact_projections"),
    )


def seal(work, out):
    planfile = work / "plan.json"
    plan = whole_iq.read(planfile)
    if plan["sources"] != trial.sources():
        raise ValueError("as-run source is different from the locked implementation")
    trial.installer.shared.verify_install(trial.BASE, plan["stock"])
    trial.installer.shared.verify_install(work / "candidate", plan["candidate"])
    authority = whole_iq.read(
        whole_iq.checked(
            trial.earlier.REPORT / "prediction-lock.json", plan["input_authority_sha256"]
        )
    )
    original = whole_iq.read(
        whole_iq.checked(
            trial.earlier.REPORT / "source-lock.json", authority["files"]["source-lock.json"]
        )
    )
    out.mkdir(exist_ok=True, parents=True)
    names, timings, witness = [], [], {}
    rows = {method: [] for method in FILES}
    for case, bind in plan["cases"].items():
        prior = original["cases"][case]["compact"]
        for method in (trial.STOCK, trial.CANDIDATE):
            folder = work / case / method
            measured = validate_record(plan, planfile, folder, case, method)
            row = dict(
                id=case,
                method=method,
                native_sha256=bind["native_sha256"],
                input_sha256=bind["input_sha256"],
                catalog_sha256=bind["catalogue_sha256"],
                capture_era_native_sha256=bind["original_native_sha256"],
                tile=prior["tile"],
                cohort="development" if case in trial.DESIGN else "held",
                result=measured["result"],
            )
            if any(row[k] != prior[k] for k in MATCH):
                raise ValueError("prediction changed authenticated wide factors")
            rows[method].append(row)
            resource = resources(measured)
            if method == trial.STOCK and row["result"]["status"] == "ok":
                resource["stock_matches_archived_wide_science"] = scientific_payload(
                    row["result"]
                ) == scientific_payload(prior["result"])
            else:
                resource["stock_matches_archived_wide_science"] = None
            timings.append(resource)
            for name in ("receipt.json", "service.log"):
                file = folder / name
                names.append(wrap(file, out / f"{case}-{method}-{name}.gz"))
        if case in trial.DESIGN:
            folder = work / case / trial.WITNESS
            run = validate_record(plan, planfile, folder, case, trial.WITNESS)
            witness[case] = run
            if COMMON.sha(work / case / "stock.prof") != plan["profile_hashes"][case]:
                raise ValueError("development profile evidence changed")
            names.append(wrap(work / case / "stock.prof", out / f"{case}-profile.prof.gz"))
            names.append(wrap(folder / "service.log", out / f"{case}-witness.log.gz"))
    for method, name in FILES.items():
        pack(out / name, rows[method])
        names.append(name)
    save_json(out / "resources.json", timings)
    csv_file(out / "resources.csv", timings)
    save_json(out / "candidate-witness.json", witness)
    save_json(out / "profile-summary.json", plan["profiles"])
    write(out / "source-lock.json", planfile.read_bytes())
    original_text = (trial.BASE / fit_basis.TARGET).read_text().splitlines(keepends=True)
    revised_text = (work / "candidate" / fit_basis.TARGET).read_text().splitlines(keepends=True)
    diff = unified_diff(
        original_text,
        revised_text,
        fromfile="a/" + fit_basis.TARGET,
        tofile="b/" + fit_basis.TARGET,
    )
    write(out / "installed-change.patch", "".join(diff).encode())
    names.extend(
        [
            "resources.json",
            "resources.csv",
            "candidate-witness.json",
            "profile-summary.json",
            "source-lock.json",
            "installed-change.patch",
        ]
    )
    save_json(
        out / "prediction-lock.json",
        dict(cases=list(trial.CASES), files={name: COMMON.sha(out / name) for name in names}),
    )


def without_work(result):
    arms, metrics = scientific_payload(result)
    metrics.pop("compact_projections", None)
    return result.get("boundary"), result.get("reason"), arms, metrics


def score(out):
    lock = COMMON.seal(out, "prediction-lock.json", FILES.values())
    data = {m: read_predictions(out / file) for m, file in FILES.items()}
    truth, _ = _frozen_roof()
    rows, parity = [], {}
    for case in lock["cases"]:
        a, b = (data[m][case] for m in (trial.STOCK, trial.CANDIDATE))
        COMMON.require_fields(b, {key: a[key] for key in MATCH})
        original, changed = a["result"], b["result"]
        parity[case] = dict(
            stock=original["status"],
            candidate=changed["status"],
            exact_except_timing_and_projection_count=(
                without_work(original) == without_work(changed)
                if original["status"] == changed["status"] == "ok"
                else None
            ),
        )
        for entry in (a, b):
            result = entry["result"]
            for arm in ARMS:
                branch = result["arms"][arm]
                rows.append(
                    dict(
                        id=case,
                        arm=arm,
                        method=entry["method"],
                        status=result["status"],
                        error_km=distance_km(branch["latlon"], truth[case]["truth"]),
                        conditional_RMS_hz=branch.get("rf_rms_hz"),
                        frequency_objective=result["metrics"].get(f"{arm}_frequency_score"),
                    )
                )
    csv_file(out / "scores.csv", rows)
    save_json(out / "parity.json", parity)
    names = ("scores.csv", "parity.json", "prediction-lock.json")
    checks = lock["files"] | {name: COMMON.sha(out / name) for name in names}
    charts = []
    for group in ("development", "held"):
        cases = [case for case in lock["cases"] if data[trial.STOCK][case]["cohort"] == group]
        receipt = f"figure-lock-{group}.json"
        save_json(out / receipt, dict(cases=cases, files=checks))
        charts.append(
            dict(
                id="wide-fit-basis-" + group,
                method=trial.CANDIDATE,
                scope="roof",
                cases=cases,
                seal=receipt,
                title=f"Compact v5 with fused Doppler and phase moments · {group}",
                caption=(
                    "Same complete archived wide factors and causal catalogue, capped at 512 MiB. "
                    "The four original v5 references use their capture-era factors."
                ),
                provenance=["candidate-witness.json", "resources.csv", "scores.csv", "parity.json"],
                series=[
                    dict(
                        key=key,
                        file=FILES[method],
                        where={"cohort": group},
                        value=method,
                        label=label,
                        native_field="capture_era_native_sha256",
                        **({"match": list(MATCH)} if method == trial.STOCK else {}),
                    )
                    for key, method, label in (
                        ("one", trial.CANDIDATE, "Fused sufficient-statistic pass"),
                        ("stock", trial.STOCK, "Original compact phase-release"),
                    )
                ],
            )
        )
    save_json(out / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--out", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    report = local_output(args.out)
    seal(args.work, report)
    score(report)
