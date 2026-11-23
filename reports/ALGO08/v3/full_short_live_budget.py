"""Charge the region-first numerical solve in the historical 55-recording sensitivity model."""

import argparse
import json
from pathlib import Path

from acquisition_throughput import gates, minimum_rate


HERE = Path(__file__).resolve().parent / "measurements"


def maximum_fraction(rows, rate, overhead):
    def accepted(fraction):
        return max(gates(rows, rate, fraction, startup_s=overhead)) <= .5

    if not accepted(0.):
        return None
    if accepted(1.):
        return 1.
    low, high = 0., 1.
    for _ in range(48):
        middle = (low + high) / 2
        if accepted(middle):
            low = middle
        else:
            high = middle
    return low


def evaluate(solver_path):
    calibration = json.loads((HERE / "full-short-seal-scaling.json").read_bytes())
    rows = json.loads((HERE / "acquisition-throughput.json").read_bytes())["rows"]
    verified = json.loads(solver_path.read_bytes())
    if verified["case"] != "DS30-0008" or not verified["valid"]:
        raise ValueError("Expected the verified dense live solver comparison")
    clocks = {arm: verified["runs"][arm]["solve"]["cpu_s"] for arm in ("installed", "control")}
    fraction = clocks["control"] / clocks["installed"]
    estimates = []
    for measurement in calibration["projections"]["receiver"]:
        if measurement["arm"] != "full-short":
            continue
        cost = measurement["measurements"]
        rate = cost["reader_MB_s"]
        for condition in ("optimistic", "stressed"):
            seal = calibration["shared_once_per_recording_tails_s"][condition]
            overhead = seal + cost["worker_overhead_s"]
            allowance = maximum_fraction(rows, rate, overhead)
            estimates.append(dict(pair=measurement["pair"], seal=condition, reader_MB_s=rate, overhead_s=overhead,
                                  median_and_summed=gates(rows, rate, fraction, startup_s=overhead),
                                  gate_reader_MB_s=[minimum_rate(rows, fraction, i, startup_s=overhead) for i in (0, 1)],
                                  maximum_solver_fraction=allowance,
                                  dense_solve_budget_s=None if allowance is None else allowance*clocks["installed"]))
    return dict(recordings=len(rows), unchanged_uninstrumented=sum(r["stages"][0] == 0 for r in rows),
                dense_solve_cpu_s=clocks, fraction=fraction, estimates=estimates)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("solver_receipt", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    with args.output.open("x") as stream:
        json.dump(evaluate(args.solver_receipt), stream, indent=2, allow_nan=False)
        stream.write("\n")
