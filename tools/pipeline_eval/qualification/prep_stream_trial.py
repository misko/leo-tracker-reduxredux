"""Sealed comparison of full v5 from paired ordinary factors at the preparation boundary."""

import argparse
import json
from functools import partial
from pathlib import Path
from unittest.mock import patch

from ..__main__ import ROOT, local_output, save_json
from ..variants import prep_stream_sky, v5_catalogue_memory, v5_lean
from . import early_memory_trial, stream_recovery_trial, working_memory_trial
from .full_v5_check import _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/refinement/prep-stream"
RUNS = Path("/srv/bulk/leo-dev/receiver-screening-20261119/prep-stream")
WORKER = Path(__file__).with_name("prep_stream_worker.py")
METHODS = {"control": "v5_armijo_aligned_finish", "stream": prep_stream_sky.METHOD}
PLAN = {"DS26-0036": (10, ("control", "stream")), "DS29-0082": (11, ("stream", "control"))}
CAP = 360
EXCLUDE = {"prep_stream_measurement"}


def source():
    frozen = v5_lean.SOURCE / "leo"
    bound = stream_recovery_trial.seal()["source"]
    paths = (
        Path(__file__),
        WORKER,
        Path(prep_stream_sky.__file__),
        Path(v5_catalogue_memory.__file__),
        Path(early_memory_trial.__file__),
        WORKER.with_name("early_memory_worker.py"),
        WORKER.with_name("stream_recovery_publish.py"),
        frozen / "operations/localization_v3_inputs.py",
        frozen / "application/localization_v3.py",
    )
    return dict(
        sources=dict(bound, **{p.name: _sha(p) for p in paths}),
        frozen=v5_lean.SOURCE_SHA256,
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        whole_iq_lock=_sha(working_memory_trial.PRIOR / "prediction-lock.json"),
        plan={c: [cpu, list(order)] for c, (cpu, order) in PLAN.items()},
        cap_s=CAP,
    )


def compare(original, control, candidate):
    receipt = original(control, candidate)
    if receipt["status"] != ["ok", "ok"]:
        return receipt
    different = set(receipt["decision_difference_keys"])
    receipt["decision_difference_keys"] = sorted(different - EXCLUDE)
    receipt["resource_difference_keys"] += sorted(different & EXCLUDE)
    receipt["decisions_exact"] = not receipt["decision_difference_keys"]
    evidence = [
        r["result"]["metrics"]["prep_stream_measurement"]["evidence"] for r in (control, candidate)
    ]
    receipt["prepared_evidence_exact"] = {k: evidence[0][k] == evidence[1][k] for k in evidence[0]}
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "replay", "publish", "score"))
    p.add_argument("--case", choices=PLAN)
    for name, default in (("report", REPORT), ("runs", RUNS), ("raw", working_memory_trial.RAW)):
        p.add_argument("--" + name, type=local_output, default=default)
    args = p.parse_args()
    original = early_memory_trial.compare
    with patch.multiple(
        early_memory_trial,
        METHODS=METHODS,
        PLAN=PLAN,
        CAP=CAP,
        WORKER=WORKER,
        source_lock=source,
        compare=partial(compare, original),
    ):
        if args.action == "seal":
            path = args.report / "source-lock.json"
            if path.exists() and json.loads(path.read_bytes()) != source():
                raise ValueError("refuse to replace an existing source seal")
            if not path.exists():
                save_json(path, source())
        elif args.action == "replay":
            if not args.case:
                p.error("--case required")
            early_memory_trial.replay(args.case, args.runs, args.report, args.raw)
        elif args.action == "publish":
            early_memory_trial.publish(args.runs, args.report)
        else:
            early_memory_trial.score(args.report)


if __name__ == "__main__":
    main()
