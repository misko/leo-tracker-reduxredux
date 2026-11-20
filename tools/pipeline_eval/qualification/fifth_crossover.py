"""Run four fixed whole-IQ fifth-center crossover services."""

import argparse
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import diagnostic_whole as diagnostic
from . import differential_runtime as runtime
from . import whole_center_union as union
from . import whole_center_union_candidate as activation
from . import whole_center_union_raw, whole_fftw_raw, whole_fftw_trial
from .full_v5_check import _sha

REPORT = union.REPORT.with_name("fifth-crossover")
WORK = Path("/var/tmp/leo-fifth-crossover-20261119")
MODULE = "tools.pipeline_eval.qualification.fifth_crossover"
DIAGNOSTIC_PIN = "f65d7ff0bfe6225acadbfb12bf3a200014fbe8d57b622b2d071509623b9204c8"
HELD_FFTW_PIN = "808045eb0314e83b56a1b2c911a4c73942c5de5d2710ab1f614542493da4fbe9"
HELD_STOCK_PIN = "e46441f38312a61a4febff38c15d06a2a4bb53a3037ddcc84c1bc95f50d53671"
CORES = {
    "DS26-0168": [4, 5],
    "DS29-0604": [6, 7],
    "DS26-0237": [12, 13],
    "DS29-0082": [12, 13],
}
METHOD = "fifth_crossover_union"
CONTROL = "fifth_crossover_stock"
REPLACE = "fifth_crossover_fourth_replace"


def checked_parent(folder, digest):
    file = whole_iq.checked(folder / "prediction-lock.json", digest)
    seal = whole_iq.read(file)
    source = whole_iq.read(
        whole_iq.checked(folder / "source-lock.json", seal["files"]["source-lock.json"])
    )
    return seal, source


def freeze(work):
    report_lock = REPORT / "source-lock.json"
    if report_lock.exists():
        raise FileExistsError(report_lock)
    _, own = activation.candidate_lock(union.WORK)
    work.mkdir(parents=True, exist_ok=False)
    copied = work / "runtime"
    copied.mkdir()
    assets = {}
    for name, original in own["assets"].items():
        path = Path(original["path"])
        assets[name] = activation.copy_checked(path, copied / path.name, original["sha256"])
    d_seal, d_plan = checked_parent(diagnostic.REPORT, DIAGNOSTIC_PIN)
    h_seal, h_plan = checked_parent(whole_fftw_trial.REPORT, HELD_FFTW_PIN)
    s_seal, _ = checked_parent(whole_fftw_trial.prior.REPORT, HELD_STOCK_PIN)
    if set(h_seal["cases"]) | set(d_seal["cases"]) != set(CORES) or set(h_seal["cases"]) != set(
        s_seal["cases"]
    ):
        raise ValueError("the original controlled roster changed")
    if any(
        plan["detectors"]["scout"]["sha256"] != assets["scout"]["sha256"]
        for plan in (d_plan, h_plan)
    ):
        raise ValueError("the prior fourth-center arms used a different FFTW scout")
    cases = {}
    for ident, cpus in CORES.items():
        cohort = "development diagnostic" if ident in d_plan["cases"] else "previous held"
        prior = (d_plan if cohort == "development diagnostic" else h_plan)["cases"][ident]
        case, _ = whole_iq.binding(ident)
        if (
            case["request"]["sha256"] != prior["request_sha256"]
            or case["recording"] != prior["recording"]
        ):
            raise ValueError("original recorded segments or truth-free request changed")
        cases[ident] = dict(prior, cpus=cpus, cohort=cohort)
    candidates = own["sources"] | {str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__))}
    lock = dict(
        cases=cases,
        receiver=d_plan["receiver"],
        receiver_files=d_plan["receiver_files"],
        native_sources=d_plan["native_sources"],
        limit_s=450,
        memory_max=whole_iq.MEMORY,
        swap_max=0,
        detectors={"candidate": assets["candidate"]},
        assets=assets,
        programs=candidates,
        original_overwrite_sha256=d_plan["detectors"]["candidate"]["sha256"],
        original_stock_sha256=d_plan["detectors"]["control"]["sha256"],
        files={
            str(path.relative_to(ROOT)): _sha(path)
            for path in (
                diagnostic.REPORT / "prediction-lock.json",
                whole_fftw_trial.REPORT / "prediction-lock.json",
                whole_fftw_trial.prior.REPORT / "prediction-lock.json",
                union.REPORT / activation.PIN,
                REPORT / "PROTOCOL.md",
            )
        },
    )
    save_json(work / "source-lock.json", lock)
    save_json(report_lock, lock)
    print(_sha(report_lock), flush=True)


def source(work):
    path = REPORT / "source-lock.json"
    lock = whole_iq.read(whole_iq.checked(work / path.name, _sha(path)))
    for name, digest in (lock["files"] | lock["programs"]).items():
        whole_iq.checked(ROOT / name, digest)
    for row in lock["assets"].values():
        whole_iq.checked(Path(row["path"]), row["sha256"])
    return lock


def activate(lock):
    return patch.multiple(
        runtime,
        MODULE=MODULE,
        HINTED_SHA256=lock["assets"]["candidate"]["sha256"],
        differential_runtime_raw=whole_center_union_raw,
        source_identity=lambda: dict(lock["programs"]),
    )


def run(work, ident):
    lock = source(work)
    if ident == "DS29-0082" and not any(
        (work / "DS26-0237" / name).is_file()
        for name in ("candidate/service.json", "candidate-failure.json")
    ):
        raise ValueError("the prior scheduled service must finish before reusing 12/13")
    with activate(lock):
        union.service(work, ident, "candidate", lock, evaluator=runtime.evaluate)


def worker(attempt):
    lock = source(attempt.parents[1])
    whole_fftw_raw.library(Path(lock["assets"]["candidate"]["path"]))
    with activate(lock):
        runtime.worker(attempt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "worker", *CORES))
    parser.add_argument("attempt", type=local_output, nargs="?")
    parser.add_argument("--work", type=local_output, default=WORK)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.action == "worker":
        worker(args.attempt)
    else:
        run(args.work, args.action)
