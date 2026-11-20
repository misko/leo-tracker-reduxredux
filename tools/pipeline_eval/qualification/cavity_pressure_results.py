"""Preserve the capped attempts and score both calibration arms after sealing."""

import argparse
import gzip
import json
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import cavity_pressure_bundle as bundle
from . import cavity_pressure_trial as trial
from . import fractional_runtime_whole as fractional
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import ORDINARY, _frozen_roof

COMMON = trial.direct.common
FILES = {trial.CANDIDATE: "positions.jsonl.gz", trial.CONTROL: "stock-positions.jsonl.gz"}
CASES = tuple(trial.PINS)


def verify_attempt(row, expected, plan, files, service_log):
    COMMON.require_fields(row, expected | {"bundle_files": files, "plan_sha256": COMMON.sha(plan)})
    if row["log_sha256"] != COMMON.sha(service_log):
        raise ValueError("service log does not match the terminal attempt")
    measured = row["measurements"]
    if len(measured["observer"]) != 1 or not row["live"] or not measured["stage"]:
        raise ValueError("capped attempt lacks stage, observer or sampled counters")
    observer = measured["observer"][0]
    if observer["pin"] != row["cpu"] or not (23.5 <= observer["parts"]["anon"] / 1024**2 <= 24.5):
        raise ValueError("persistent observer does not match the intended in-service charge")
    samples = [*row["live"], *(point for group in measured.values() for point in group)]
    if any(
        s["memory.max"] != trial.probe.MEMORY
        or s["memory.swap.max"] != 0
        or s["memory.swap.current"] != 0
        for s in samples
    ):
        raise ValueError("inconsistent physical memory cap")
    validate_result(row["result"])
    status = row["service_result"]
    if status == "success" and (
        row["returncode"] != 0 or len(measured["finish"]) != 1 or measured["finish"][0]["evaluator"]
    ):
        raise ValueError("incomplete direct inference authority")
    if status == "oom-kill" and (
        row["kernel"]["MemoryPeak"] != str(trial.probe.MEMORY)
        or row["kernel"]["Result"] != status
        or row["result"]["status"] != "failed"
    ):
        raise ValueError("kernel does not establish the recorded 512 MiB OOM")
    if status != "success" and any(row["result"]["arms"][arm]["latlon"] for arm in ARMS):
        raise ValueError("failed service cannot supply geographic endpoints")
    if row["wall_s"] > trial.LIMIT + 5:
        raise ValueError("attempt breached the intended supervisor bound")
    return samples


def stage_totals(stages):
    def intervals(name):
        open_stage = None
        for stage in stages:
            if stage["operation"] != name:
                continue
            if stage["event"] == "start":
                open_stage = stage
            elif open_stage:
                yield stage["cpu_s"] - open_stage["cpu_s"]
                open_stage = None

    return {
        name: sum(intervals(name))
        for name in dict.fromkeys(stage["operation"] for stage in stages)
        if any(stage["operation"] == name and stage["event"] == "return" for stage in stages)
    }


def measurements(row, samples):
    peak = row["kernel"].get("MemoryPeak", "")
    cpu = row["kernel"].get("CPUUsageNSec", "")
    stage = row["measurements"]["stage"]
    finish = row["measurements"]["finish"]
    return dict(
        id=row["id"],
        method=row["method"],
        cpu_pin=row["cpu"],
        service_status=row["service_result"],
        position_status=row["result"]["status"],
        wall_s=row["wall_s"],
        charged_peak_bytes=(
            int(peak) if peak.isdecimal() else max(s["memory.peak"] for s in samples)
        ),
        sampled_anonymous_peak_bytes=max(s["parts"]["anon"] for s in samples),
        sampled_file_peak_bytes=max(s["parts"]["file"] for s in samples),
        resident_worker_peak_kib=finish[0]["rss_peak_kib"] if finish else None,
        cpu_s=int(cpu) / 1e9 if cpu.isdecimal() else max(s["cpu_s"] for s in samples),
        observer_anonymous_bytes=row["measurements"]["observer"][0]["parts"]["anon"],
        last_named_stage=stage[-1]["operation"],
        last_named_event=stage[-1]["event"],
        last_named_cpu_s=stage[-1]["cpu_s"],
        completed_stage_cpu_s=stage_totals(stage),
    )


def save_archived(path, dest):
    write(dest, gzip.compress(path.read_bytes(), compresslevel=6, mtime=0))
    return dest.name


def seal(work, initial_transport, out):
    plan_file, candidate_file = work / "plan.json", work / "candidate-lock.json"
    plan, candidate = COMMON.read(plan_file), COMMON.read(candidate_file)
    if (
        plan["source"] != trial.sources()
        or trial.bindings() != plan["bindings"]
        or candidate["plan_sha256"] != COMMON.sha(plan_file)
        or candidate["source_recipe_sha256"] != COMMON.sha(Path(bundle.__file__))
        or whole_iq.receiver_identity(work / "candidate") != candidate["files"]
        or candidate["changed"] != sorted((bundle.TARGET, bundle.MANIFEST))
        or any(
            COMMON.sha(work / "candidate" / f) != candidate["compiler_sources"][f]
            for f in bundle.COMPILER_SOURCES
        )
    ):
        raise ValueError("the completed trial differs from its sealed source or input")
    out.mkdir(parents=True, exist_ok=True)
    stock_authority = COMMON.read(ORDINARY / "recording-receipts.json")["recordings"]
    whole = trial.ORIGINAL
    whole_plan = COMMON.read(whole / "plan.json")
    reserve = CASES[0]
    reserve_native = plan["bindings"][reserve]["native"]
    native_parity = fractional.verify_native(
        COMMON.read(Path(reserve_native)),
        stock_authority[reserve]["native_sha256"],
        whole_plan["detector_sha256"],
    )
    save_json(out / "native-parity.json", native_parity)
    whole_receipt = COMMON.read(whole / "service.json")
    whole_log = whole / "service.log"
    if whole_receipt["log_sha256"] != COMMON.sha(whole_log):
        raise ValueError("original full-IQ service loss is unverified")
    save_json(
        out / "original-whole-iq.json",
        dict(
            start=COMMON.read(whole / "start.json"),
            **plan["bindings"][reserve]["original_failure"],
            native_sha256=plan["bindings"][reserve]["native_sha256"],
        ),
    )
    write(out / "original-whole-iq.log", whole_log.read_bytes())
    names = ["original-whole-iq.json", "original-whole-iq.log", "native-parity.json"]
    rows, resources = {key: [] for key in FILES}, []
    for case in CASES:
        left = plan["bindings"][case]
        for method in (trial.CONTROL, trial.CANDIDATE):
            folder = work / "runs" / case / method
            path, log = folder / "attempt.json", folder / "service.log"
            row = COMMON.read(path)
            expected = dict(left, method=method, cpu=trial.PINS[case])
            files = plan["files"] if method == trial.CONTROL else candidate["files"]
            samples = verify_attempt(row, expected, plan_file, files, log)
            resources.append(measurements(row, samples))
            label = "released" if method == trial.CANDIDATE else "stock"
            for kept in (path, log):
                names.append(save_archived(kept, out / f"{case}-{label}-{kept.name}.gz"))
            rows[method].append(
                dict(
                    id=case,
                    method=method,
                    tile=left["tile"],
                    native_sha256="sha256:" + left["native_sha256"],
                    paired_ordinary_sha256=stock_authority[case]["native_sha256"],
                    input_sha256=left["request_sha256"],
                    catalog_sha256=left["catalog_sha256"],
                    result=row["result"],
                )
            )
        bad = initial_transport / "runs" / case / trial.CANDIDATE
        log, path = bad / "service.log", bad / "attempt.json"
        startup = COMMON.read(path)
        if (
            startup["measurements"]["stage"]
            or startup["log_sha256"] != COMMON.sha(log)
            or "FileNotFoundError" not in log.read_text()
        ):
            raise ValueError("initial transport failure did not occur at the expected boundary")
        for kept in (path, log):
            names.append(save_archived(kept, out / f"{case}-transport-{kept.name}.gz"))
    for key, path in FILES.items():
        pack(out / path, rows[key])
        names.append(path)
    for name, src in (
        ("source-lock.json", plan_file),
        ("candidate-lock.json", candidate_file),
        ("initial-transport-lock.json", initial_transport / "candidate-lock.json"),
    ):
        write(out / name, src.read_bytes())
        names.append(name)
    save_json(out / "resources.json", resources)
    names.append("resources.json")
    save_json(
        out / "receipt.json",
        dict(cases=CASES, files={name: COMMON.sha(out / name) for name in names}),
    )


def scientific_payload(result):
    return result["arms"], {k: v for k, v in result["metrics"].items() if k != "stage_s"}


def plot_pressure(out):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.ticker import MultipleLocator

    figure = Figure(figsize=(11, 4.4), layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots(1, len(CASES), sharey=True)
    for ident, axis in zip(CASES, axes, strict=True):
        for label, name, color in (
            ("Original", "stock", "#ad5731"),
            ("Release completed phases", "released", "#186c7c"),
        ):
            path = out / f"{ident}-{name}-attempt.json.gz"
            data = json.loads(gzip.decompress(path.read_bytes()))
            live = data["live"]
            cpu = [s["cpu_s"] for s in live]
            sizes = [s["memory.current"] / 2**20 for s in live]
            end = data["service_result"]
            axis.plot(cpu, sizes, color=color, linewidth=1.5, label=label)
            axis.plot(cpu[-1], sizes[-1], marker="x" if end == "oom-kill" else ".", color=color)
            if ident == CASES[0] and name == "stock":
                for event, annotation in (
                    ("signed_context.py/signed_context", "Signed context"),
                    ("family_cavity.py/cavity_policy", "Cavity proposals"),
                ):
                    began = next(
                        s["cpu_s"]
                        for s in data["measurements"]["stage"]
                        if s["operation"] == event and s["event"] == "start"
                    )
                    axis.axvline(began, color="#656565", linestyle=":", linewidth=0.8)
                    axis.text(
                        began - 0.5,
                        43 if event.startswith("family_cavity") else 100,
                        annotation,
                        rotation=90,
                        fontsize=8,
                        va="bottom",
                        ha="right",
                    )
        axis.axhline(512, color="#252525", linestyle="--", linewidth=1, label="512 MiB service cap")
        axis.set(
            title=f"{ident} · {'reserve' if ident == CASES[0] else 'ordinary control'}",
            xlabel="Cgroup CPU time (s)",
            ylim=(0, 545),
            xlim=(0, None),
        )
        axis.yaxis.set_major_locator(MultipleLocator(128))
        axis.grid(axis="y", alpha=0.24)
    axes[0].set_ylabel("Charged cgroup memory (MiB)")
    axes[1].legend(loc="upper left", frameon=False, fontsize=8)
    figure.savefig(out / "memory-by-stage.png", dpi=170)


def score(out):
    seal = COMMON.seal(out, "receipt.json", FILES.values())
    truth, _ = _frozen_roof()
    methods = {method: read_predictions(out / name) for method, name in FILES.items()}
    scores, parity = [], {}
    for ident in CASES:
        a, b = (methods[m][ident] for m in (trial.CONTROL, trial.CANDIDATE))
        COMMON.require_fields(
            a, {field: b[field] for field in ("input_sha256", "native_sha256", "catalog_sha256")}
        )
        stock, candidate = a["result"], b["result"]
        matched = stock["status"] == candidate["status"] == "ok"
        parity[ident] = dict(
            stock_status=stock["status"],
            candidate_status=candidate["status"],
            exact_scientific_payload=(
                scientific_payload(stock) == scientific_payload(candidate) if matched else None
            ),
        )
        for row in (a, b):
            result = row["result"]
            for arm in ARMS:
                fitted = result["arms"][arm]
                scores.append(
                    dict(
                        id=ident,
                        method=row["method"],
                        status=result["status"],
                        arm=arm,
                        location_error_km=distance_km(fitted["latlon"], truth[ident]["truth"]),
                        conditional_rms_hz=fitted.get("rf_rms_hz"),
                        frequency_objective=result["metrics"].get(f"{arm}_frequency_score"),
                    )
                )
    csv_file(out / "scores.csv", scores)
    save_json(out / "parity.json", parity)
    plot_pressure(out)
    extra = ("scores.csv", "parity.json", "memory-by-stage.png")
    files = {**seal["files"], **{f: COMMON.sha(out / f) for f in extra}}
    save_json(out / "figure-lock.json", dict(cases=CASES, files=files))
    repeated = ["tile", "input_sha256", "native_sha256", "catalog_sha256"]
    series = [
        dict(
            key=key,
            value=method,
            file=FILES[method],
            label=label,
            native_field="paired_ordinary_sha256",
            native_authority="ordinary",
            **({"match": repeated} if method == trial.CONTROL else {}),
        )
        for key, method, label in (
            ("one", trial.CANDIDATE, "Release constrained phase models"),
            ("stock", trial.CONTROL, "Original compact receiver"),
        )
    ]
    chart = dict(
        id="cavity-phase-pressure",
        method=trial.CANDIDATE,
        scope="roof",
        cases=CASES,
        seal="figure-lock.json",
        title="Compact v5 phase-model lifetime at the 512 MiB cap",
        caption=(
            "Matched stored factors, truth-free requests and physical memory limits. "
            "Stock reserve OOM stays in both arm denominators. Original v5 used capture-era GLRT."
        ),
        provenance=[
            "resources.json",
            "scores.csv",
            "parity.json",
            "memory-by-stage.png",
            "original-whole-iq.json",
        ],
        series=series,
    )
    save_json(out / "figures.json", dict(version=1, charts=[chart]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("initial_transport", type=Path)
    parser.add_argument("--out", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    target = local_output(args.out)
    seal(args.work, args.initial_transport, target)
    score(target)
