"""Verify final-use cache eviction with matched native-to-final scientific receipts."""

import argparse
import json
from functools import partial
from pathlib import Path
from unittest.mock import patch

from ..__main__ import ROOT, local_output, save_json
from ..variants import history_stream_prep, v5_lean
from . import early_memory_trial, prep_stream_trial, working_memory_trial
from .full_v5_check import _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/refinement/history-stream"
RUNS = Path("/srv/bulk/leo-dev/receiver-screening-20261119/history-stream")
WORKER = Path(__file__).with_name("history_stream_worker.py")
METHODS = {"control": "prep_stream_sky", "history": history_stream_prep.METHOD}
PLAN = {"DS26-0036": (4, ("control", "history")), "DS29-0082": (5, ("history", "control"))}
CAP = 300


def source():
    prior = prep_stream_trial.source()
    expected = json.loads((prep_stream_trial.REPORT / "source-lock.json").read_bytes())
    if expected != prior:
        raise ValueError("earlier prep-stream scientific source changed")
    sources = (
        Path(__file__),
        WORKER,
        Path(history_stream_prep.__file__),
        v5_lean.SOURCE / "leo/analysis/localization_v3/elements.py",
    )
    return dict(
        sources=dict(prior["sources"], **{p.name: _sha(p) for p in sources}),
        frozen=v5_lean.SOURCE_SHA256,
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        prep_stream_lock_sha256=_sha(prep_stream_trial.REPORT / "source-lock.json"),
        whole_iq_lock=prior["whole_iq_lock"],
        plan={c: [cpu, list(order)] for c, (cpu, order) in PLAN.items()},
        cap_s=CAP,
    )


def compare(original, control, candidate):
    receipt = prep_stream_trial.compare(original, control, candidate)
    if receipt["status"] != ["ok", "ok"]:
        return receipt
    receipt["resource_difference_keys"].append("history_stream_cache")
    receipt["decision_difference_keys"] = [
        k for k in receipt["decision_difference_keys"] if k != "history_stream_cache"
    ]
    receipt["decisions_exact"] = not receipt["decision_difference_keys"]
    cache = candidate["result"]["metrics"]["history_stream_cache"]
    if len(cache) != 1 or cache[0]["released_entries"] == 0:
        raise ValueError("candidate did not execute final-use cache drain")
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
