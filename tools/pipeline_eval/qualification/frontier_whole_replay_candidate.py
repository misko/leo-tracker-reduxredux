"""Activate one independently qualified acquisition candidate for the frozen study."""

import argparse
import gzip
import json
import shutil
from pathlib import Path

from .. import iq_compare, iq_service, whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from . import differential_runtime as differential
from . import frontier_whole_replay as study
from .full_v5_check import _sha

PILOT = study.REPORT.parent / "differential-pilot"
BUILD = Path("/home/mouse9911/.cache/leo-hinted-glrt-20261119/build-lock.json")
SCOUT = "tools/pipeline_eval/variants/differential_pilot.py"


def check_gate(groups, targets):
    misses, retained, confirm = (
        groups[key] for key in ("primary_miss", "primary_matched", "confirmation")
    )
    if (
        (misses["n"], retained["n"], confirm["n"]) != (16, 8, 8)
        or misses["causal_physical_passes"] < 2
        or retained["causal_physical_passes"] < 7
        or confirm["causal_physical_passes"] < 2
        or {row["case"].split("-")[0] for row in targets} != {"DS26", "DS29"}
    ):
        raise ValueError("differential pilot failed the independently measured activation gate")


def candidate_assets():
    seal = whole_iq.read(PILOT / "prediction-lock.json")
    evidence = {
        name: whole_iq.checked(PILOT / name, seal["files"][name])
        for name in ("qualification.json", "input-lock.json.gz")
    }
    raw_inputs = json.loads(gzip.decompress(evidence["input-lock.json.gz"].read_bytes()))
    whole_iq.checked(ROOT / SCOUT, raw_inputs["sources"][SCOUT])
    qualification = whole_iq.read(evidence["qualification.json"])
    check_gate(qualification["groups"], qualification["confirmation_targets"])
    build = whole_iq.read(BUILD)
    expected = dict(stock=study.STOCK_SHA, hinted=differential.HINTED_SHA256)
    if build["library_sha256"] != expected:
        raise ValueError("the hinted binary does not bind the qualified stock detector")
    library = whole_iq.checked(Path(build["paths"]["hinted"]), expected["hinted"])
    build_receipt = whole_iq.checked(
        library.parent / "build-receipt.json", build["hinted_receipt_sha256"]
    )
    return library, {
        "pilot-prediction-lock.json": PILOT / "prediction-lock.json",
        "pilot-qualification.json": evidence["qualification.json"],
        "pilot-input-lock.json.gz": evidence["input-lock.json.gz"],
        "hinted-build-lock.json": BUILD,
        "hinted-build-receipt.json": build_receipt,
    }


def activate(base):
    lock = study.prospective(base)
    library, receipts = candidate_assets()
    fixed = base / "wide-differential.so"
    shutil.copyfile(library, fixed)
    whole_iq.checked(fixed, differential.HINTED_SHA256)
    for name, path in receipts.items():
        write(study.REPORT / name, path.read_bytes())
    activation = dict(
        policy="unprivileged-differential",
        programs=differential.source_identity()
        | {str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__))},
        receipt_files={name: _sha(path) for name, path in receipts.items()},
        prospective_lock_sha256=_sha(study.REPORT / "prospective-lock.json"),
    )
    spec = dict(
        lock["spec"],
        candidate=dict(sha256=differential.HINTED_SHA256, label="Differential pilot hint"),
        activation=activation,
    )
    spec_path = study.REPORT / "experiment.json"
    save_json(spec_path, spec)
    iq_compare.prepare(
        spec_path,
        study.PROTOCOL,
        Path(lock["receiver"]),
        dict(control=Path(lock["detectors"]["control"]["path"]), candidate=fixed),
        base / "candidate-plan",
    )
    plan = whole_iq.read(base / "candidate-plan/source-lock.json")
    for key in lock.keys() - {"spec", "detectors"}:
        if lock[key] != plan[key]:
            raise ValueError(f"candidate activation changed the frozen stock authority: {key}")
    if lock["detectors"]["control"] != plan["detectors"]["control"]:
        raise ValueError("candidate activation changed the frozen stock detector")
    path = base / "runs/source-lock.json"
    save_json(path, dict(plan, activation=activation))
    write(path.with_suffix(".sha256"), (_sha(path) + "\n").encode())


def run(base, ident):
    work = base / "runs"
    lock = whole_iq.read(
        whole_iq.checked(
            work / "source-lock.json", (work / "source-lock.sha256").read_text().strip()
        )
    )
    planned, folder = lock["cases"][ident], work / ident
    for name, digest in (lock["activation"]["programs"] | lock["programs"]).items():
        whole_iq.checked(ROOT / name, digest)
    for name, digest in lock["activation"]["receipt_files"].items():
        whole_iq.checked(study.REPORT / name, digest)
    if not any(
        (folder / name).is_file() for name in ("control/service.json", "control-failure.json")
    ):
        raise ValueError("the stock attempt must have a terminal state before starting its pair")
    receiver = Path(lock["receiver"])
    if whole_iq.receiver_identity(receiver) != lock["receiver_files"]:
        raise ValueError("installed phase release differs from the frozen plan")
    detector = lock["detectors"]["candidate"]
    attempt = folder / "candidate"
    if attempt.exists():
        raise FileExistsError(attempt)
    try:
        differential.evaluate(
            ident,
            Path(detector["path"]),
            detector["sha256"],
            receiver,
            attempt,
            planned["cpus"],
            lock["limit_s"],
        )
    except (FileExistsError, iq_service.UnsettledService):
        raise
    except (OSError, RuntimeError, ValueError) as error:
        if (attempt / "service.log").exists() and not (attempt / "service.json").exists():
            raise iq_service.UnsettledService(
                f"terminal state unconfirmed for {attempt}"
            ) from error
        save_json(folder / "candidate-failure.json", dict(error=str(error)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("activate")
    commands.add_parser("run").add_argument("--case", required=True)
    parser.add_argument("base", type=local_output)
    args = parser.parse_args()
    if args.command == "activate":
        activate(args.base)
    else:
        run(args.base, args.case)


if __name__ == "__main__":
    main()
