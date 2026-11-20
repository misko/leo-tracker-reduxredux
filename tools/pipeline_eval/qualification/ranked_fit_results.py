"""Seal exact paired position output and ordered nomination evidence."""

import argparse
import gzip
from difflib import unified_diff
from hashlib import sha256
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import ranked_fit_trial as trial
from .cavity_pressure_results import scientific_payload
from .fractional_runtime_whole import verify_native
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import ORDINARY, _frozen_roof

COMMON = trial.COMMON
FILES = {trial.STOCK: "stock-positions.jsonl.gz", trial.CANDIDATE: "positions.jsonl.gz"}
MATCH = ["input_sha256", "native_sha256", "catalog_sha256", "tile"]


def kernel_bounds(row, plan):
    probes = [row[key] for key in ("ready", "finish") if key in row]
    if row["service_status"] == "success" and len(probes) != 2:
        raise ValueError("successful process lacks cap evidence at both ends")
    if any(
        x["memory.max"] != plan["memory_bytes"] or x["memory.swap.max"] or x["memory.swap.current"]
        for x in probes
    ):
        raise ValueError("receiver did not retain its declared physical service limits")
    if "ready" in row and (row["ready"]["cpu"] != row["cpu"] or row["ready"]["nice"] < 10):
        raise ValueError("unexpected service affinity or nice level")
    validate_result(row["result"])


def timing(row):
    nomination = row.get("nomination", {})
    calls, times = (nomination.get(key, {}) for key in ("calls", "cpu_s"))
    out = row.get("finish", {})
    terminal_high = row["service_kernel"].get("MemoryPeak", "")
    terminal_cpu = row["service_kernel"].get("CPUUsageNSec", "")
    peak = out.get("memory.peak", int(terminal_high) if terminal_high.isdecimal() else None)
    return dict(
        id=row["id"],
        method=row["method"],
        status=row["result"]["status"],
        cpu_pin=row["cpu"],
        order=row["order"],
        supervisor_wall_s=row["wall_s"],
        process_cpu_s=out.get("cpu_s"),
        kernel_cpu_s=(int(terminal_cpu) / 1e9 if terminal_cpu.isdecimal() else None),
        charged_peak_bytes=peak,
        worker_rss_peak_kib=out.get("rss_peak_kib"),
        nomination_cpu_s=times.get("nominate"),
        fine_cpu_s=times.get("candidate"),
        coarse_cpu_s=times.get("screen"),
        family_model_cpu_s=times.get("family_data"),
        mode_with_support_cpu_s=times.get("mode_with_support", 0.0) if nomination else None,
        mode_without_support_cpu_s=times.get("mode_without_support", 0.0) if nomination else None,
        mode_with_support=calls.get("mode_with_support", 0) if nomination else None,
        mode_without_support=calls.get("mode_without_support", 0) if nomination else None,
        candidates_without_modes=calls.get("candidates_without_modes", 0) if nomination else None,
        fine_candidates=calls.get("candidate"),
        families=nomination.get("families"),
    )


def seal(work, out, *, cases=None):
    planfile, candidatefile = work / "plan.json", work / "candidate-lock.json"
    plan, candidate = COMMON.read(planfile), COMMON.read(candidatefile)
    cases = tuple(trial.CASES) if cases is None else cases
    if (
        plan["sources"] != trial.sources()
        or candidate["plan_sha256"] != COMMON.sha(planfile)
        or candidate["changed"] != sorted((trial.MANIFEST, trial.TARGET))
    ):
        raise ValueError("installed source differs from its prescoring lock")
    trial.shared.verify_install(work / "stock", plan["stock_install"])
    trial.shared.verify_install(work / "candidate", candidate)
    authorities = COMMON.read(ORDINARY / "recording-receipts.json")["recordings"]
    rows, captures, profiles = {method: [] for method in FILES}, {}, {}
    times, names = [], []
    out.mkdir(exist_ok=True, parents=True)
    for ident in cases:
        bound = trial.shared.binding(ident)
        if bound != plan["cases"][ident]:
            raise ValueError("saved native/causal factor binding changed")
        original = authorities[ident]["native_sha256"]
        profiles[ident] = verify_native(
            COMMON.read(Path(bound["native"])), original, bound["detector_sha256"]
        )
        captures[ident] = {}
        for method in plan["order"][ident]:
            src = work / "runs" / ident / method
            receipt, log = src / "attempt.json", src / "service.log"
            install = plan["stock_install"] if method == trial.STOCK else candidate
            row = COMMON.read(receipt)
            COMMON.require_fields(
                row,
                bound
                | dict(
                    plan_sha256=COMMON.sha(planfile),
                    source_install=install,
                    method=method,
                    cpu=plan["cpus"][ident],
                    order=plan["order"][ident].index(method),
                    log_sha256=COMMON.sha(log),
                ),
            )
            kernel_bounds(row, plan)
            captures[ident][method] = row.get("nomination")
            times.append(timing(row))
            rows[method].append(
                dict(
                    id=ident,
                    method=method,
                    tile=bound["tile"],
                    paired_ordinary_sha256=original,
                    input_sha256=bound["request_sha256"],
                    native_sha256="sha256:" + bound["native_sha256"],
                    catalog_sha256=bound["catalog_sha256"],
                    cohort=(
                        "companion"
                        if "companion" in plan
                        else "held"
                        if ident == trial.HELD
                        else "development"
                    ),
                    result=row["result"],
                )
            )
            for path in (receipt, log):
                name = f"{ident}-{method}-{path.name}.gz"
                write(out / name, gzip.compress(path.read_bytes(), mtime=0))
                names.append(name)
    for method, name in FILES.items():
        pack(out / name, rows[method])
        names.append(name)
    write(out / "source-lock.json", planfile.read_bytes())
    write(out / "candidate-lock.json", candidatefile.read_bytes())
    original, revised = (
        (work / method / trial.TARGET).read_text().splitlines(keepends=True)
        for method in ("stock", "candidate")
    )
    changes = unified_diff(
        original, revised, fromfile="a/" + trial.TARGET, tofile="b/" + trial.TARGET
    )
    write(out / "installed-change.patch", "".join(changes).encode())
    save_json(out / "nominations.json", captures)
    save_json(out / "native-authority.json", profiles)
    csv_file(out / "resources.csv", times)
    names.extend(
        [
            "source-lock.json",
            "candidate-lock.json",
            "installed-change.patch",
            "nominations.json",
            "resources.csv",
            "native-authority.json",
        ]
    )
    if "companion" in plan:
        launcher = (work / "launcher.py.gz").read_bytes()
        if sha256(gzip.decompress(launcher)).hexdigest() != plan["companion"]["source_sha256"]:
            raise ValueError("companion launch source differs from the pre-inference plan")
        write(out / "launcher.py.gz", launcher)
        names.append("launcher.py.gz")
    save_json(
        out / "receipt.json",
        dict(cases=list(cases), files={name: COMMON.sha(out / name) for name in names}),
    )


def score(out, *, cohorts=("development", "held")):
    seal = COMMON.seal(out, "receipt.json", FILES.values())
    predictions = {method: read_predictions(out / name) for method, name in FILES.items()}
    comparisons, scored = {}, []
    truth, _ = _frozen_roof()
    nom = COMMON.read(out / "nominations.json")
    for ident in seal["cases"]:
        a, b = (predictions[method][ident] for method in (trial.STOCK, trial.CANDIDATE))
        COMMON.require_fields(b, {key: a[key] for key in MATCH})
        original, revised = a["result"], b["result"]
        complete = original["status"] == revised["status"] == "ok"
        p, q = (nom[ident][method] for method in (trial.STOCK, trial.CANDIDATE))
        comparisons[ident] = dict(
            original_status=original["status"],
            candidate_status=revised["status"],
            identical_reported_position_and_rf=(
                scientific_payload(original) == scientific_payload(revised) if complete else None
            ),
            identical_ordered_fine_candidates=(
                p["ordered_fine_outcomes_sha256"] == q["ordered_fine_outcomes_sha256"]
                if p and q
                else None
            ),
        )
        for row in (a, b):
            result = row["result"]
            for arm in ARMS:
                r = result["arms"][arm]
                scored.append(
                    dict(
                        id=ident,
                        arm=arm,
                        method=row["method"],
                        status=result["status"],
                        geographic_error_km=distance_km(r["latlon"], truth[ident]["truth"]),
                        conditional_RMS_hz=r.get("rf_rms_hz"),
                        frequency_objective=result["metrics"].get(f"{arm}_frequency_score"),
                    )
                )
    csv_file(out / "scores.csv", scored)
    save_json(out / "parity.json", comparisons)
    extra = ("scores.csv", "parity.json")
    files = {**seal["files"], **{f: COMMON.sha(out / f) for f in extra}}
    charts = []
    for cohort in cohorts:
        cases = [k for k in seal["cases"] if predictions[trial.STOCK][k]["cohort"] == cohort]
        lock = f"{cohort}-figure-lock.json"
        save_json(out / lock, dict(cases=cases, files=files))
        charts.append(
            dict(
                id=f"ranked-fit-cavity-{cohort}",
                method=trial.CANDIDATE,
                scope="roof",
                cases=cases,
                seal=lock,
                title=f"Ranked cavity nomination without unused modes · {cohort}",
                caption=(
                    "Same saved narrow factors, causal catalogue and offered tile. "
                    "Matched lightweight 512 MiB, zero-swap services."
                ),
                provenance=["nominations.json", "resources.csv", *extra],
                series=[
                    dict(
                        key=key,
                        file=FILES[method],
                        value=method,
                        label=label,
                        where={"cohort": cohort},
                        native_field="paired_ordinary_sha256",
                        native_authority="ordinary",
                        **({"match": MATCH} if method == trial.STOCK else {}),
                    )
                    for key, method, label in (
                        ("one", trial.CANDIDATE, "Prepare only supported orbital modes"),
                        ("stock", trial.STOCK, "Phase-release compact v5"),
                    )
                ],
            )
        )
    save_json(out / "figures.json", dict(version=1, charts=charts))


def confirmation(source, work, parent):
    ident = "DS29-0247"
    planfile = source / "plan.json"
    plan = COMMON.read(planfile)
    candidatefile = source / "candidate-lock.json"
    candidate = COMMON.read(candidatefile)
    old = source / "runs" / ident
    original = old / trial.STOCK / "attempt.json"
    missed = old / trial.CANDIDATE / "attempt.json"
    proof_path = work / "confirmation-lock.json"
    proof = COMMON.read(proof_path)
    COMMON.require_fields(
        proof,
        dict(
            development_run_plan_sha256=COMMON.sha(planfile),
            original_stock_attempt_sha256=COMMON.sha(original),
            original_timed_out_attempt_sha256=COMMON.sha(missed),
            candidate_lock_sha256=COMMON.sha(candidatefile),
            max_attempts=1,
            limit_s=plan["service_limit_s"],
            cpu=trial.CASES[ident],
            case=ident,
        ),
    )
    if COMMON.read(missed)["result"]["status"] != "timed_out":
        raise ValueError("original primary attempt is missing its sealed timeout")
    run = work / "runs" / ident / trial.CANDIDATE
    fresh, log = run / "attempt.json", run / "service.log"
    row = COMMON.read(fresh)
    COMMON.require_fields(
        row,
        plan["cases"][ident]
        | dict(
            method=trial.CANDIDATE,
            plan_sha256=COMMON.sha(planfile),
            source_install=candidate,
            log_sha256=COMMON.sha(log),
            cpu=trial.CASES[ident],
        ),
    )
    kernel_bounds(row, plan)
    out = parent / "confirmation"
    out.mkdir(exist_ok=True)
    stock = read_predictions(parent / FILES[trial.STOCK])[ident]
    rec = dict(stock, method=trial.CANDIDATE, result=row["result"])
    pack(out / "positions.jsonl.gz", [stock, rec])
    first = COMMON.read(original)
    complete = row["result"]["status"] == "ok"
    metrics = dict(
        case=ident,
        stock_primary=timing(first),
        candidate_primary=timing(COMMON.read(missed)),
        candidate_confirmation=timing(row),
        exact_scientific_payload=(
            scientific_payload(first["result"]) == scientific_payload(row["result"])
            if complete
            else None
        ),
        ordered_fine_equal=(
            first["nomination"]["ordered_fine_outcomes_sha256"]
            == row["nomination"]["ordered_fine_outcomes_sha256"]
            if row.get("nomination")
            else None
        ),
    )
    save_json(out / "comparison.json", metrics)
    write(out / "confirmation-lock.json", proof_path.read_bytes())
    write(out / "attempt.json.gz", gzip.compress(fresh.read_bytes(), mtime=0))
    write(out / "service.log", log.read_bytes())
    files = (
        "positions.jsonl.gz",
        "comparison.json",
        "confirmation-lock.json",
        "attempt.json.gz",
        "service.log",
    )
    save_json(
        out / "receipt.json",
        dict(cases=[ident], files={name: COMMON.sha(out / name) for name in files}),
    )
    chart = dict(
        id="ranked-fit-cavity-reserve-confirmation",
        method=trial.CANDIDATE,
        scope="roof",
        title="Ranked cavity · independent 185-second reserve confirmation",
        caption=(
            "Separate bounded candidate attempt after the primary reserve timeout. "
            "The original paired schedule remains in the development chart."
        ),
        cases=[ident],
        seal="receipt.json",
        provenance=["comparison.json", "confirmation-lock.json", "service.log"],
        series=[
            dict(
                key=key,
                file="positions.jsonl.gz",
                value=method,
                label=label,
                native_field="paired_ordinary_sha256",
                native_authority="ordinary",
                **({"match": MATCH} if method == trial.STOCK else {}),
            )
            for key, method, label in (
                ("one", trial.CANDIDATE, "One bounded confirmation"),
                ("stock", trial.STOCK, "Previously measured same-input stock"),
            )
        ],
    )
    save_json(out / "figures.json", dict(version=1, charts=[chart]))


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("work", type=Path)
    args.add_argument("--out", type=Path, default=trial.REPORT)
    args.add_argument("--confirmation", type=Path)
    args.add_argument("--companion", type=Path)
    p = args.parse_args()
    result = local_output(p.out)
    if p.confirmation:
        confirmation(p.work.resolve(), p.confirmation.resolve(), result)
    elif p.companion:
        from .ranked_fit_companion import CASE

        result = result / "companion"
        seal(p.companion.resolve(), result, cases=(CASE,))
        score(result, cohorts=("companion",))
    else:
        seal(p.work.resolve(), result)
        score(result)
