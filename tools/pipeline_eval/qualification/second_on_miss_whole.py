"""Run the physical second-on-miss policy through the frozen whole-IQ service."""

import argparse
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from .. import iq_service, whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants import second_on_miss
from ..variants.selective_capture import visit_pairs
from . import one_lane_whole as prior
from . import second_on_miss_whole_raw as raw
from .full_v5_check import _sha

REPORT = prior.REPORT.with_name("second-on-miss-whole")
WORK = Path("/var/tmp/leo-second-on-miss-whole-20261119")
METHOD = "second_on_miss_whole"
MODULE = "tools.pipeline_eval.qualification.second_on_miss_whole"
CASES = {"DS26-0014": [12, 13], "DS29-0082": [14, 15]}


def freeze(work):
    if (REPORT / "source-lock.json").exists():
        raise FileExistsError("the raw and position inputs are already frozen")
    receipt = prior.REPORT / "prediction-lock.json"
    seal = whole_iq.read(receipt)
    required = (
        "source-lock.json",
        "positions.jsonl.gz",
        "resources.json",
        "parity.json",
        "stock-runtime.json",
    )
    for name in required:
        whole_iq.checked(prior.REPORT / name, seal["files"][name])
    parent = prior.source(prior.WORK)
    if list(parent["cases"]) != list(CASES) or not all(
        rows["same_native_bytes"] for rows in whole_iq.read(prior.REPORT / "parity.json").values()
    ):
        raise ValueError("the original single-lane reports differ from their dual-stock projection")
    work.mkdir(parents=True, exist_ok=False)
    cases, binaries = {}, {}
    for ident, cores in CASES.items():
        base = parent["cases"][ident]
        case, request = whole_iq.binding(ident)
        if (
            case["native"]["sha256"] != base["capture_native_sha256"]
            or case["recording"] != base["recording"]
            or case["request"]["sha256"] != base["request_sha256"]
            or case["catalog"]["sha256"] != base["catalog_sha256"]
            or request["causal_snapshots"] != base["orbit_snapshots"]
            or case["regions"][0] != base["tile"]
        ):
            raise ValueError("raw waveform, causal position request or offer differs from controls")
        library = work / "libraries" / ident / "wide-stock.so"
        library.parent.mkdir(parents=True)
        dispatch = library.with_name("dispatch.json")
        binary = parent["detectors"][ident]
        for source, target in ((binary, library), (base["dispatch"], dispatch)):
            shutil.copyfile(whole_iq.checked(Path(source["path"]), source["sha256"]), target)
            target.chmod(0o644)
            whole_iq.checked(target, source["sha256"])
        cases[ident] = dict(
            base, cpus=cores, dispatch=dict(path=str(dispatch), sha256=base["dispatch"]["sha256"])
        )
        binaries[ident] = dict(path=str(library), sha256=binary["sha256"])
    owned = (
        Path(__file__),
        Path(raw.__file__),
        Path(second_on_miss.__file__),
        REPORT / "PROTOCOL.md",
    )
    plan = dict(
        parent,
        cases=cases,
        detectors=binaries,
        policy=second_on_miss.POLICY,
        prior_one_receipt_sha256=_sha(receipt),
        programs=parent["programs"] | {str(p.relative_to(ROOT)): _sha(p) for p in owned},
    )
    for root in (work, REPORT):
        path = root / "source-lock.json"
        save_json(path, plan)
        path.chmod(0o644)


def source(work):
    path = REPORT / "source-lock.json"
    lock = whole_iq.read(whole_iq.checked(work / path.name, _sha(path)))
    for name, digest in lock["programs"].items():
        whole_iq.checked(ROOT / name, digest)
    return lock


def trace(folder):
    combined = []
    for lane in (0, 1):
        log = folder / f"replayed-{lane}.log"
        lines = [
            line.removeprefix(raw.TRACE)
            for line in log.read_text().splitlines()
            if line.startswith(raw.TRACE)
        ]
        if len(lines) != 1:
            raise ValueError("native raw lane did not publish exactly one observed decision footer")
        combined.extend(json.loads(lines[0]))
    return sorted(combined)


def verify_dispatch(document, planned, actual):
    if len(actual) != len(planned):
        raise ValueError("actual gate decisions do not cover each originally valid visit")
    for (visit, primary, used_partner), row, (index, probes) in zip(
        actual, planned, visit_pairs(document["source"]["probes"]), strict=True
    ):
        if (visit, primary) != (row["visit"], row["selected_receiver"]) or visit != index:
            raise ValueError("physical receiver priority differs from its frozen schedule")
        if type(used_partner) is not bool or used_partner != second_on_miss.needs_partner(
            probes[primary]
        ):
            raise ValueError("measured partner use does not match the emitted primary gate")
        if not used_partner and probes[1 - primary]["candidates"]:
            raise ValueError("an unmeasured partner contains observed candidates")


def worker(attempt):
    lock = source(attempt.parents[1])
    case = lock["cases"][attempt.parent.name]
    dispatch = case["dispatch"]
    planned = whole_iq.read(whole_iq.checked(Path(dispatch["path"]), dispatch["sha256"]))
    original = whole_iq.recording.native_document

    def assembled(*args, **kwargs):
        doc, counts = original(*args, **kwargs)
        actual = trace(attempt / "recording")
        verify_dispatch(doc, planned, actual)
        save_json(attempt / "actual-dispatch.json", actual)
        return second_on_miss.mark(doc, doc["source"]["probes"]), counts

    raw_path = SimpleNamespace(__name__=raw.__name__, mark=whole_iq.raw.mark)
    with (
        patch.multiple(whole_iq, raw=raw_path, MODULE=MODULE),
        patch.object(whole_iq.recording, "native_document", assembled),
    ):
        whole_iq.worker(attempt)


def run(work, ident):
    lock = source(work)
    with patch.object(whole_iq, "MODULE", MODULE), patch.object(iq_service, "MODULE", MODULE):
        prior.union.service(
            work, ident, "candidate", dict(lock, detectors={"candidate": lock["detectors"][ident]})
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("freeze", "run", "worker", "position"))
    p.add_argument("value", nargs="?")
    p.add_argument("--work", default=WORK, type=local_output)
    args = p.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.action == "run":
        run(args.work, args.value)
    elif args.action == "worker":
        worker(local_output(args.value))
    else:
        whole_iq.position(local_output(args.value))
