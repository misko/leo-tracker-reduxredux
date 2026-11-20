"""Activate and run only the independently qualified fifth-center compiled detector."""

import argparse
import shutil
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import differential_runtime as runtime
from . import whole_center_union as trial
from . import whole_center_union_raw, whole_fftw_raw, whole_fftw_runtime, whole_fftw_trial
from .full_v5_check import _sha

MODULE = "tools.pipeline_eval.qualification.whole_center_union_candidate"
INITIAL_PIN = "candidate-lock.json"
PIN = "candidate-lock-v2.json"
GATE = "qualification-lock.json"
GATE_SHA256 = "5030388da34eb00091c886ef6268eb7f44c2b11ff2159c57adb1160f6b7e46cc"


def copy_checked(source, destination, digest):
    shutil.copyfile(whole_iq.checked(source, digest), destination)
    whole_iq.checked(destination, digest)
    return dict(path=str(destination), sha256=digest)


def freeze(work, evidence):
    original = trial.source(work)
    if (trial.REPORT / PIN).exists():
        raise FileExistsError("the candidate is already activated")
    evidence = Path(evidence).resolve()
    gate = whole_iq.read(whole_iq.checked(evidence, GATE_SHA256))
    if not all(gate[key] for key in ("passed", "null_stock_exact", "stock_peaks_preserved")):
        raise ValueError("full-IQ candidate requires passing independent native qualification")
    for name, checksum in gate["files"].items():
        whole_iq.checked(evidence.parent / name, checksum)
    for name, checksum in gate["sources"].items():
        whole_iq.checked(ROOT / name, checksum)
    if gate["entry"] != "leo_native_glrt_analyze_center_union_v1":
        raise ValueError("compiled qualification uses an unrecognized center-union entry")
    candidate = gate["detector"]
    fftw = whole_fftw_trial.qualified()["fftw"]
    if gate["sidecar"]["sha256"] != fftw["sha256"]:
        raise ValueError("native qualification and replay must use the same FFTW scout")
    paths = work / "center-union-runtime-v2"
    paths.mkdir()
    candidate_copy = copy_checked(
        Path(candidate["path"]),
        paths / "libleo-adaptive-detector.so",
        candidate["sha256"],
    )
    scout_copy = copy_checked(
        Path(fftw["path"]),
        paths / whole_fftw_raw.SCOUT_NAME,
        fftw["sha256"],
    )
    closure = (
        whole_fftw_runtime.source_identity()
        | gate["sources"]
        | {
            str(path.relative_to(ROOT)): _sha(path)
            for path in (Path(__file__), Path(whole_center_union_raw.__file__))
        }
    )
    lock = dict(
        stock_plan_sha256=_sha(work / "source-lock.json"),
        authority_sha256=_sha(evidence),
        authority=str(evidence),
        assets=dict(candidate=candidate_copy, scout=scout_copy),
        sources=closure,
        entry=gate["entry"],
        cases=list(original["cases"]),
        initial_activation_sha256=_sha(trial.REPORT / INITIAL_PIN),
        previous_activation_note=(
            "Initial CLI exited during activation after copying assets. No service launched."
        ),
    )
    whole_iq.checked(trial.REPORT / GATE, GATE_SHA256)
    save_json(work / PIN, lock)
    save_json(trial.REPORT / PIN, lock)


def candidate_lock(work):
    stock = trial.source(work)
    path = trial.REPORT / PIN
    lock = whole_iq.read(whole_iq.checked(work / PIN, _sha(path)))
    if lock["stock_plan_sha256"] != _sha(work / "source-lock.json"):
        raise ValueError("candidate activation changed the frozen matched stock plan")
    if lock["cases"] != list(stock["cases"]):
        raise ValueError("candidate activation changed the frozen waveform roster")
    whole_iq.checked(Path(lock["authority"]), lock["authority_sha256"])
    whole_iq.checked(trial.REPORT / GATE, lock["authority_sha256"])
    for path, checksum in lock["sources"].items():
        whole_iq.checked(ROOT / path, checksum)
    for asset in lock["assets"].values():
        whole_iq.checked(Path(asset["path"]), asset["sha256"])
    return stock, lock


def activate(lock):
    return patch.multiple(
        runtime,
        MODULE=MODULE,
        HINTED_SHA256=lock["assets"]["candidate"]["sha256"],
        differential_runtime_raw=whole_center_union_raw,
        source_identity=lambda: dict(lock["sources"]),
    )


def candidate(work, ident):
    study, lock = candidate_lock(work)
    control = work / ident / "control/service.json"
    if not control.is_file() and not (work / ident / "control-failure.json").is_file():
        raise ValueError("stock service must be terminal before its matched candidate")
    study["detectors"]["candidate"] = lock["assets"]["candidate"]
    with activate(lock):
        trial.service(work, ident, "candidate", study, evaluator=runtime.evaluate)


def worker(attempt):
    _, lock = candidate_lock(attempt.parents[1])
    whole_fftw_raw.library(Path(lock["assets"]["candidate"]["path"]))
    with activate(lock):
        runtime.worker(attempt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    choices = parser.add_subparsers(dest="action", required=True)
    freeze_args = choices.add_parser("freeze")
    freeze_args.add_argument("--evidence", required=True, type=Path)
    freeze_args.add_argument("--work", default=trial.WORK, type=local_output)
    service = choices.add_parser("run")
    service.add_argument("--case", required=True)
    service.add_argument("--work", default=trial.WORK, type=local_output)
    choices.add_parser("worker").add_argument("attempt", type=local_output)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work, args.evidence)
    elif args.action == "worker":
        worker(args.attempt)
    else:
        candidate(args.work, args.case)
