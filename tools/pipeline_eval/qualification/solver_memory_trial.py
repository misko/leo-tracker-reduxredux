"""Seal and compare the ordinary native-to-final tiled salvage measurements."""

import argparse
import json
from functools import partial
from pathlib import Path
from unittest.mock import patch

from ..__main__ import ROOT, local_output, save_json
from ..variants import v5_lean, v5_tiled_salvage
from . import early_memory_trial, history_stream_trial, working_memory_trial
from .full_v5_check import _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/refinement/solver-memory"
RUNS = Path("/srv/bulk/leo-dev/receiver-screening-20261119/solver-memory")
WORKER = Path(__file__).with_name("solver_memory_worker.py")
METHODS = {"control": "history_stream_prep", "tile": v5_tiled_salvage.METHOD}
PLAN = {"DS26-0036": (4, ("control", "tile")), "DS29-0082": (5, ("tile", "control"))}
CAP = 300


def source():
    previous = history_stream_trial.source()
    history = history_stream_trial.REPORT / "source-lock.json"
    if json.loads(history.read_bytes()) != previous:
        raise ValueError("history preparation differs from its source seal")
    paths = (
        Path(__file__),
        WORKER,
        Path(v5_tiled_salvage.__file__),
        v5_lean.SOURCE / "leo/analysis/localization_v3/conservative_recovery.py",
    )
    return dict(
        sources=dict(previous["sources"], **{p.name: _sha(p) for p in paths}),
        frozen=v5_lean.SOURCE_SHA256,
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        preparation_lock_sha256=_sha(history),
        whole_iq_lock=previous["whole_iq_lock"],
        cap_s=CAP,
        plan={k: [cpu, list(order)] for k, (cpu, order) in PLAN.items()},
    )


def compare(original, a, b):
    verdict = history_stream_trial.compare(original, a, b)
    if verdict["status"] != ["ok", "ok"]:
        return verdict
    keys = ("solver_memory",)
    verdict["resource_difference_keys"] += [
        k for k in verdict["decision_difference_keys"] if k in keys
    ]
    verdict["decision_difference_keys"] = [
        k for k in verdict["decision_difference_keys"] if k not in keys
    ]
    verdict["decisions_exact"] = not verdict["decision_difference_keys"]
    one, two = [r["result"]["metrics"]["solver_memory"] for r in (a, b)]
    verdict["roster_order_exact"] = one["rankings"] == two["rankings"]
    verdict["salvage_outcome_exact"] = one["outcomes"] == two["outcomes"]
    verdict["salvage_windows"] = two["counters"].get("coarse_windows", 0)
    return verdict


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
                raise ValueError("refuse to replace an earlier source seal")
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
