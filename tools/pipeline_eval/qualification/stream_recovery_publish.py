"""Seal paired recovery decisions while retaining separate resource counters."""

import argparse
import json
from unittest.mock import patch

from ..__main__ import local_output
from ..scoring import ARMS
from . import stream_recovery_trial as trial

RESOURCE_METRICS = {
    "numerical_worker_cpu_s",
    "numerical_worker_peak_rss_kib",
    "numerical_worker_wall_s",
}


def publication_comparison(original, control, stream):
    pair = original(control, stream)
    if pair["status"] != ["ok", "ok"]:
        return pair
    different = pair["decision_difference_keys"]
    pair["resource_difference_keys"] = sorted(set(different) & RESOURCE_METRICS)
    pair["decision_difference_keys"] = sorted(set(different) - RESOURCE_METRICS)
    pair["decisions_exact"] = not pair["decision_difference_keys"]
    metrics = [r["result"]["metrics"] for r in (control, stream)]
    optimizers = [
        {k: v for k, v in m["position_optimizer"].items() if k != "wall_s"} for m in metrics
    ]
    pair["optimizer_work_exact"] = optimizers[0] == optimizers[1]
    pair["frequency_objectives_exact"] = {
        arm: metrics[0].get(arm + "_frequency_score") == metrics[1].get(arm + "_frequency_score")
        for arm in ARMS
    }
    return pair


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs", type=local_output, default=trial.RUNS)
    p.add_argument("--report", type=local_output, default=trial.REPORT)
    args = p.parse_args()
    original = trial.compare

    def compare(control, stream):
        return publication_comparison(original, control, stream)

    with patch.object(trial, "compare", compare):
        print(json.dumps(trial.publish(args.runs, args.report), indent=2))


if __name__ == "__main__":
    main()
