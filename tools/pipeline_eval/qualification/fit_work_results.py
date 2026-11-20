"""Seal measured factor-to-position pairs and publish both calibration arms."""

import argparse
import gzip
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import fit_work_bundle as overlay
from . import fit_work_profile as profiling
from . import fit_work_trial as trial
from .cavity_pressure_results import scientific_payload
from .fractional_runtime_whole import verify_native
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import ORDINARY, _frozen_roof

COMMON = trial.COMMON
FILES = {trial.CANDIDATE: "positions.jsonl.gz", trial.STOCK: "stock-positions.jsonl.gz"}


def verify(row, plan_file, case, method, plan, manifest, log):
    COMMON.require_fields(
        row,
        plan["cases"][case]
        | dict(
            method=method,
            cpu=plan["pins"][case],
            order=plan["orders"][case].index(method),
            plan_sha256=COMMON.sha(plan_file),
            install=manifest,
            log_sha256=COMMON.sha(log),
        ),
    )
    samples = row["samples"]
    if (
        row["wall_s"] > plan["limit_s"] + 5
        or not samples
        or any(
            s["memory.max"] != plan["memory"] or s["memory.swap.max"] or s["memory.swap.current"]
            for s in samples
        )
        or row["peak_bytes"] != max(s["memory.peak"] for s in samples)
    ):
        raise ValueError("missing proof of measured core or memory limit")
    validate_result(row["result"])
    if row["service_result"] != "success" and any(
        row["result"]["arms"][arm]["latlon"] is not None for arm in ARMS
    ):
        raise ValueError("failed service must have null geographic positions")


def seal(work, out):
    plan_file = work / "plan.json"
    candidate_file = work / "candidate-lock.json"
    plan, candidate = map(COMMON.read, (plan_file, candidate_file))
    if (
        plan["source"] != trial.protocol_source()
        or candidate["plan_sha256"] != COMMON.sha(plan_file)
        or candidate["source_recipe_sha256"] != COMMON.sha(Path(overlay.__file__))
        or candidate["files"][overlay.KERNEL]
        != COMMON.sha(Path(overlay.fit_work_projection.__file__))
    ):
        raise ValueError("plan, staged source or work contract differs from the frozen inputs")
    trial.verify_install(Path(plan["stock_root"]), plan["stock"])
    trial.verify_install(work / "candidate", candidate)
    ordinary = COMMON.read(ORDINARY / "recording-receipts.json")["recordings"]
    rows, runtime, authority, names = {key: [] for key in FILES}, [], {}, []
    out.mkdir(exist_ok=True, parents=True)
    for case in trial.CASES:
        binding = trial.binding(case)
        if binding != plan["cases"][case]:
            raise ValueError("archived factor binding changed")
        native = ordinary[case]["native_sha256"]
        authority[case] = verify_native(
            COMMON.read(Path(binding["native"])), native, binding["detector_sha256"]
        )
        for method in plan["orders"][case]:
            path = work / "runs" / case / method
            log = path / "service.log"
            receipt = path / "attempt.json"
            row = COMMON.read(receipt)
            base = plan["stock"] if method == trial.STOCK else candidate
            verify(row, plan_file, case, method, plan, base, log)
            rows[method].append(
                dict(
                    id=case,
                    method=method,
                    tile=row["tile"],
                    catalog_sha256=row["catalog_sha256"],
                    input_sha256=row["request_sha256"],
                    native_sha256="sha256:" + row["native_sha256"],
                    paired_ordinary_sha256=native,
                    result=row["result"],
                )
            )
            runtime.append(
                {
                    k: row[k]
                    for k in ("id", "method", "cpu", "order", "wall_s", "cpu_s", "peak_bytes")
                }
                | {
                    "status": row["result"]["status"],
                    "service": row["service_result"],
                    "cavity_wall_s": row["result"]["metrics"].get("stage_s", {}).get("cavity"),
                }
            )
            for source in (receipt, log):
                name = f"{case}-{method}-{source.name}.gz"
                write(out / name, gzip.compress(source.read_bytes(), compresslevel=6, mtime=0))
                names.append(name)
    for method, name in FILES.items():
        pack(out / name, rows[method])
    save_json(out / "native-authority.json", authority)
    csv_file(out / "resources.csv", runtime)
    write(out / "source-lock.json", plan_file.read_bytes())
    write(out / "candidate-lock.json", candidate_file.read_bytes())
    names.extend(
        [
            *FILES.values(),
            "native-authority.json",
            "resources.csv",
            "source-lock.json",
            "candidate-lock.json",
        ]
    )
    save_json(
        out / "receipt.json",
        dict(cases=list(trial.CASES), files={name: COMMON.sha(out / name) for name in names}),
    )


def score(out):
    seal = COMMON.seal(out, "receipt.json", FILES.values())
    methods = {method: read_predictions(out / name) for method, name in FILES.items()}
    refs, _ = _frozen_roof()
    scores, parity = [], {}
    for case in seal["cases"]:
        a, b = (methods[method][case] for method in (trial.STOCK, trial.CANDIDATE))
        fields = ("tile", "input_sha256", "native_sha256", "catalog_sha256")
        COMMON.require_fields(a, {name: b[name] for name in fields})
        stock, candidate = a["result"], b["result"]
        complete = stock["status"] == candidate["status"] == "ok"
        parity[case] = dict(
            original_status=stock["status"],
            candidate_status=candidate["status"],
            exact_scientific_payload=(
                scientific_payload(stock) == scientific_payload(candidate) if complete else None
            ),
            position_difference_m={
                arm: 1000
                * distance_km(stock["arms"][arm]["latlon"], candidate["arms"][arm]["latlon"])
                if complete
                else None
                for arm in ARMS
            },
        )
        for row in (a, b):
            result = row["result"]
            for arm, endpoint in result["arms"].items():
                scores.append(
                    dict(
                        id=case,
                        method=row["method"],
                        status=result["status"],
                        arm=arm,
                        error_km=distance_km(endpoint["latlon"], refs[case]["truth"]),
                        conditional_rms_hz=endpoint.get("rf_rms_hz"),
                        frequency_objective=result["metrics"].get(f"{arm}_frequency_score"),
                    )
                )
    csv_file(out / "scores.csv", scores)
    save_json(out / "parity.json", parity)
    extra = ("scores.csv", "parity.json")
    files = {**seal["files"], **{f: COMMON.sha(out / f) for f in extra}}
    save_json(out / "figure-lock.json", dict(cases=seal["cases"], files=files))
    chart = dict(
        id="constrained-cavity-phase-fit-work",
        method=trial.CANDIDATE,
        scope="roof",
        cases=seal["cases"],
        seal="figure-lock.json",
        title="Compact v5 with prepared time-domain position gates",
        caption=(
            "Physical 512 MiB, zero-swap factor-to-position pairs on the same narrow-band input, "
            "causal catalogue and offer. Includes one development reserve and two held recordings. "
            "Original v5 used the capture-era detector."
        ),
        provenance=["resources.csv", *extra],
        series=[
            dict(
                key=key,
                file=FILES[method],
                value=method,
                label=label,
                native_field="paired_ordinary_sha256",
                native_authority="ordinary",
                **(
                    {"match": ["tile", "input_sha256", "native_sha256", "catalog_sha256"]}
                    if method == trial.STOCK
                    else {}
                ),
            )
            for key, method, label in (
                ("one", trial.CANDIDATE, "Fixed residual-gate projection"),
                ("stock", trial.STOCK, "Phase-release compact v5"),
            )
        ],
    )
    save_json(out / "figures.json", dict(version=1, charts=[chart]))


def profile(stock, candidate, out):
    install = COMMON.read(out / "candidate-lock.json")
    if install["development_profile_sha256"] != COMMON.sha(stock / "profile.prof"):
        raise ValueError("wrong original development profiler")
    data = {"stock": profiling.metrics(stock / "profile.prof")}
    receipt = COMMON.read(candidate / "profile-receipt.json")
    if (
        receipt["source_sha256"] != COMMON.sha(out / "candidate-lock.json")
        or receipt["log_sha256"] != COMMON.sha(candidate / "profile.log")
        or receipt["result_sha256"] != COMMON.sha(candidate / "result.json")
    ):
        raise ValueError("wrong candidate profile file or installation")
    data["candidate"] = receipt["statistics"]
    data["candidate_returncode"] = receipt["returncode"]
    for label, path in (("stock", stock), ("candidate", candidate)):
        write(out / f"profile-{label}.log", (path / "profile.log").read_bytes())
    save_json(out / "profile.json", data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--out", type=Path, default=trial.REPORT)
    parser.add_argument("--profiles", nargs=2, type=Path)
    arg = parser.parse_args()
    dest = local_output(arg.out)
    if arg.profiles:
        profile(*arg.profiles, dest)
    else:
        seal(arg.work, dest)
        score(dest)
