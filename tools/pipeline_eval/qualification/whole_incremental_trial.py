"""Replay one compiled stock-first rescue on each authenticated fifth-center recording."""

import argparse
import shutil
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import differential_runtime as runtime
from . import whole_center_union as parent
from . import whole_incremental_raw
from .full_v5_check import _sha

REPORT = parent.REPORT.parent / "whole-incremental-rescue"
WORK = Path("/srv/bulk/leo-dev/receiver-screening-20261119/whole-incremental-rescue")
MODULE = "tools.pipeline_eval.qualification.whole_incremental_trial"
CORES = {"DS26-0197": [16, 17], "DS29-0316": [22, 23]}
METHOD = "whole_incremental_rescue"
LIMIT = 450
PARENT_PIN = "14ab3e27d00c79c090896a55c6d9340fe6eb2c99077d59ddfbc0f4d0a1a31c6a"
FEATURE_PIN = "c797705e500d58870e6b4cc62dc1c4faa946181b51786c1e4aff3c627fc94162"


def checked_receipt():
    path = parent.REPORT / "prediction-lock.json"
    receipt = whole_iq.read(whole_iq.checked(path, PARENT_PIN))
    if receipt["cases"] != list(CORES):
        raise ValueError("the complete stock/fifth holdout differs")
    for name in (
        "source-lock.json",
        "selection.json",
        "positions.jsonl.gz",
        "visits.jsonl.gz",
        "resources.json",
        "candidate-lock-v2.json",
    ):
        whole_iq.checked(parent.REPORT / name, receipt["files"][name])
    return receipt


def stages(ident, receipt):
    bindings = {}
    for role in ("control", "candidate"):
        prefix = parent.WORK / ident / role
        raw = whole_iq.read(prefix / "raw.json")
        terminal = whole_iq.read(prefix / "service.json")
        if not whole_iq.iq_service.succeeded(terminal):
            raise ValueError("historical complete IQ control lacks authenticated success")
        whole_iq.checked(prefix / "recording/native.json", raw["native_sha256"])
        whole_iq.checked(prefix / "recording/request.json", raw["request_sha256"])
        native = f"native/{role}/{ident}.json.gz"
        whole_iq.checked(parent.REPORT / native, receipt["files"][native])
        names = ("raw.json", "service.json", "position.json", "plan.json", "end.json")
        bindings[role] = dict(
            path=str(prefix),
            files={name: _sha(prefix / name) for name in names},
            archived_native=receipt["files"][native],
        )
    return bindings


def freeze(work):
    if (REPORT / "input-lock.json").exists():
        raise FileExistsError("the prospective roster is already locked")
    receipt = checked_receipt()
    source = whole_iq.read(parent.REPORT / "source-lock.json")
    receiver = Path(source["receiver"])
    if (
        whole_iq.receiver_identity(receiver) != source["receiver_files"]
        or whole_iq.native_sources(receiver) != source["native_sources"]
    ):
        raise ValueError("installed compact phase-release receiver changed")
    cases, control = {}, {}
    for ident, cores in CORES.items():
        case, request = whole_iq.binding(ident)
        frozen = source["cases"][ident]
        if (
            case["native"]["sha256"] != frozen["capture_native_sha256"]
            or case["request"]["sha256"] != frozen["request_sha256"]
            or case["catalog"]["sha256"] != frozen["catalog_sha256"]
            or case["recording"] != frozen["recording"]
            or request["causal_snapshots"] != frozen["orbit_snapshots"]
            or case["regions"][0] != frozen["tile"]
        ):
            raise ValueError("recording, offer or causal identity differs from the saved controls")
        cases[ident] = dict(frozen, cpus=cores)
        control[ident] = stages(ident, receipt)
    work.mkdir(parents=True, exist_ok=False)
    lock = dict(
        cases=cases,
        control=control,
        receiver=str(receiver),
        receiver_files=source["receiver_files"],
        native_sources=source["native_sources"],
        memory_max=whole_iq.MEMORY,
        swap_max=0,
        limit_s=LIMIT,
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        control_prediction_lock_sha256=PARENT_PIN,
    )
    save_json(work / "input-lock.json", lock)
    save_json(REPORT / "input-lock.json", lock)


def inputs(work):
    parent_lock = REPORT / "input-lock.json"
    lock = whole_iq.read(whole_iq.checked(work / parent_lock.name, _sha(parent_lock)))
    whole_iq.checked(REPORT / "PROTOCOL.md", lock["protocol_sha256"])
    checked_receipt()
    return lock


def activate(work, release):
    """Copy the independently qualified binaries, binding exact sources before raw launch."""
    inputs(work)
    release = release.resolve()
    candidate = whole_iq.read(whole_iq.checked(release, FEATURE_PIN))
    if candidate["entry"] != "leo_native_glrt_analyze_incremental_v1" or not all(
        candidate[k]
        for k in (
            "passed",
            "null_stock_exact",
            "one_lane_scout_surface_exact",
            "stock_rows_preserved",
            "positive_gate_verified",
        )
    ):
        raise ValueError("the incremental release has no passing raw qualification")
    for name, digest in candidate["files"].items():
        whole_iq.checked(release.parent / name, digest)
    raw = whole_incremental_raw
    directory = work / "release"
    directory.mkdir()
    assets = {}
    for role, spec in (("detector", candidate["detector"]), ("scout", candidate["sidecar"])):
        path = Path(spec["path"])
        name = "libleo-adaptive-detector.so" if role == "detector" else path.name
        updated = directory / name
        shutil.copyfile(whole_iq.checked(path, spec["sha256"]), updated)
        whole_iq.checked(updated, spec["sha256"])
        assets[role] = dict(path=str(updated), sha256=spec["sha256"])
    raw_release = directory / "raw-release.json"
    save_json(raw_release, assets)
    raw_release.chmod(0o644)
    sources = (
        runtime.source_identity()
        | candidate["sources"]
        | {str(path.relative_to(ROOT)): _sha(path) for path in (Path(__file__), Path(raw.__file__))}
    )
    for path, digest in sources.items():
        whole_iq.checked(ROOT / path, digest)
    lock = dict(
        input_lock_sha256=_sha(work / "input-lock.json"),
        candidate_authority=dict(path=str(release), sha256=_sha(release)),
        raw_module=raw.__name__,
        sources=sources,
        assets=assets,
        raw_release=dict(path=str(raw_release), sha256=_sha(raw_release)),
    )
    save_json(work / "candidate-lock.json", lock)
    save_json(REPORT / "candidate-lock.json", lock)


def configured(work):
    lock = inputs(work)
    path = REPORT / "candidate-lock.json"
    config = whole_iq.read(whole_iq.checked(work / path.name, _sha(path)))
    whole_iq.checked(work / "input-lock.json", config["input_lock_sha256"])
    whole_iq.checked(
        Path(config["candidate_authority"]["path"]), config["candidate_authority"]["sha256"]
    )
    for spec in (*config["assets"].values(), config["raw_release"]):
        whole_iq.checked(Path(spec["path"]), spec["sha256"])
    for name, digest in config["sources"].items():
        whole_iq.checked(ROOT / name, digest)
    lock["detectors"] = {"candidate": config["assets"]["detector"]}
    return lock, config


def context(config):
    return patch.multiple(
        runtime,
        MODULE=MODULE,
        HINTED_SHA256=config["assets"]["detector"]["sha256"],
        differential_runtime_raw=import_module(config["raw_module"]),
        source_identity=lambda: config["sources"],
    )


def run(work, ident):
    lock, config = configured(work)
    with context(config):
        parent.service(work, ident, "candidate", lock, evaluator=runtime.evaluate)


def worker(attempt):
    _, config = configured(attempt.parents[1])
    with context(config):
        runtime.worker(attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choices = parser.add_subparsers(dest="action", required=True)
    for name in ("freeze", "activate", "run"):
        p = choices.add_parser(name)
        p.add_argument("--work", type=local_output, default=WORK)
        if name == "activate":
            p.add_argument("--release", type=local_output, required=True)
        elif name == "run":
            p.add_argument("--case", choices=CORES, required=True)
    choices.add_parser("worker").add_argument("attempt", type=local_output)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.action == "activate":
        activate(args.work, args.release)
    elif args.action == "run":
        run(args.work, args.case)
    else:
        worker(args.attempt)


if __name__ == "__main__":
    main()
