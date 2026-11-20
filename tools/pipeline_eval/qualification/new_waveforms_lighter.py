"""Run a third whole-IQ arm only after direct native scientific qualification."""

import argparse
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from . import differential_runtime as runtime
from . import new_waveforms as study
from . import whole_center_union_raw, whole_fftw_raw
from .full_v5_check import _sha

MODULE = "tools.pipeline_eval.qualification.new_waveforms_lighter"
METHOD = "new_waveforms_lighter_fifth"
PIN = "lighter-source-lock.json"
WITNESS = "lighter-qualification.json"
CANDIDATE = "lighter"


def validate_gate(gate, plan):
    if (
        gate["entry"] != "leo_native_glrt_analyze_center_union_v1"
        or gate["baseline_sha256"] != plan["detectors"]["candidate"]["sha256"]
        or gate["candidate"]["sha256"] == gate["baseline_sha256"]
        or not gate["passed"]
        or set(gate["exact_edges"]) != {"lower", "upper"}
        or not gate["candidate_rows_exact"]
        or not gate["support_and_gates_exact"]
        or gate["scout"]["sha256"] != plan["detectors"]["scout"]["sha256"]
    ):
        raise ValueError("the actual complete-replay entry lacks independent scientific parity")


def freeze(work, evidence, checksum):
    if (study.REPORT / PIN).exists():
        raise FileExistsError("the exact third library is already activated")
    with study.context():
        base = study.previous.source(work)
    witness = whole_iq.checked(evidence.resolve(), checksum)
    gate = whole_iq.read(witness)
    validate_gate(gate, base)
    for name, digest in gate["files"].items():
        whole_iq.checked(witness.parent / name, digest)
    for name, digest in gate["sources"].items():
        whole_iq.checked(ROOT / name, digest)
    folder = work / "lighter-runtime"
    folder.mkdir()
    assets = {
        key: study.previous.activated.copy_checked(
            Path(gate[key]["path"]),
            folder / name,
            gate[key]["sha256"],
        )
        for key, name in (
            ("candidate", "libleo-adaptive-detector.so"),
            ("scout", whole_fftw_raw.SCOUT_NAME),
        )
    }
    programs = (
        base["programs"]
        | gate["sources"]
        | {
            str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__)),
        }
    )
    record = dict(
        parent_sha256=_sha(study.REPORT / "source-lock.json"),
        qualification_sha256=checksum,
        qualification_path=str(witness),
        assets=assets,
        programs=programs,
        cases=list(base["cases"]),
        entry=gate["entry"],
    )
    write(study.REPORT / WITNESS, witness.read_bytes())
    save_json(study.REPORT / PIN, record)
    save_json(work / PIN, record)


def binding(work):
    with study.context():
        base = study.previous.source(work)
    source = whole_iq.read(whole_iq.checked(work / PIN, _sha(study.REPORT / PIN)))
    if source["parent_sha256"] != _sha(study.REPORT / "source-lock.json") or source[
        "cases"
    ] != list(base["cases"]):
        raise ValueError("lighter phase changed the original two-case capture lock")
    whole_iq.checked(study.REPORT / WITNESS, source["qualification_sha256"])
    for name, digest in source["programs"].items():
        whole_iq.checked(ROOT / name, digest)
    for asset in source["assets"].values():
        whole_iq.checked(Path(asset["path"]), asset["sha256"])
    base["detectors"][CANDIDATE] = source["assets"]["candidate"]
    return base, source


def activate(lock):
    return patch.multiple(
        runtime,
        MODULE=MODULE,
        HINTED_SHA256=lock["assets"]["candidate"]["sha256"],
        differential_runtime_raw=whole_center_union_raw,
        source_identity=lambda: dict(lock["programs"]),
    )


def run(work, ident):
    original, active = binding(work)
    for role in ("control", "candidate"):
        parent = work / ident
        if (
            not (parent / role / "service.json").is_file()
            and not (parent / f"{role}-failure.json").is_file()
        ):
            raise ValueError("initial paired services must release this core pair")
    with study.previous.patched_case(original), activate(active):
        study.previous.union.service(work, ident, CANDIDATE, original, evaluator=runtime.evaluate)


def worker(attempt):
    original, active = binding(attempt.parents[1])
    whole_fftw_raw.library(Path(active["assets"]["candidate"]["path"]))
    with (
        study.previous.patched_case(original),
        patch.object(
            whole_iq.recording,
            "_load_case",
            lambda ident: study.previous.local_case(original, ident),
        ),
        activate(active),
    ):
        runtime.worker(attempt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("attempt", type=local_output, nargs="?")
    parser.add_argument("--work", type=local_output, default=study.WORK)
    parser.add_argument("--case")
    parser.add_argument("--gate", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    if args.action == "freeze" and args.gate and args.sha256:
        freeze(args.work, args.gate, args.sha256)
    elif args.action == "run" and args.case:
        run(args.work, args.case)
    elif args.action == "worker" and args.attempt:
        worker(args.attempt)
    else:
        parser.error("provide the pinned gate, one selected case or the service attempt")
