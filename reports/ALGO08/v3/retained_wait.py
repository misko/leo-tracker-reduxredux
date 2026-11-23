"""Elapsed-time budget when one-core baseline wait cannot be removed by reducing arithmetic."""

import csv
import json
from math import isclose
from statistics import median

from staged_budget import CLOCK_SHA, ROOT, TIMES_SHA, checked


def projected(stages, cpu, acquisition, solver, order):
    total = sum(stages)
    scales = (acquisition, solver, 1.)
    result = sum(s * f for s, f in zip(stages, scales, strict=True))
    if order == "scale_elapsed":
        return result
    if order not in ("best", "worst") or not 0 <= cpu <= total:
        raise ValueError("Invalid one-core wait budget")
    wait = total - cpu
    for i in sorted(range(3), key=lambda i: 1 - scales[i], reverse=order == "worst"):
        allocated = min(wait, stages[i])
        result += allocated * (1 - scales[i])
        wait -= allocated
    return result


def gates(rows, acquisition, solver, order):
    base = [sum(r["stages"]) for r in rows]
    times = [projected(r["stages"], r["cpu_s"], acquisition, solver, order) for r in rows]
    return median(t / b for t, b in zip(times, base, strict=True)), sum(times) / sum(base)


def threshold(rows, solver, order):
    if max(gates(rows, 0., solver, order)) > .5:
        return None
    lo, hi = 0., 1.
    for _ in range(45):
        mid = (lo + hi) / 2
        if max(gates(rows, mid, solver, order)) <= .5:
            lo = mid
        else:
            hi = mid
    return lo


def read_rows():
    clocks = {r["recording"]: r for r in csv.DictReader(
        checked(ROOT / "first-55/stage-clocks.csv", CLOCK_SHA).decode().splitlines())}
    rows = []
    for r in csv.DictReader(checked(ROOT / "first-55/recordings.csv", TIMES_SHA).decode().splitlines()):
        if r["build"] != "candidate":
            continue
        total, cpu = float(r["elapsed_s"]), float(r["cpu_s"])
        c = clocks.get(r["case"])
        if c is not None:
            if r["decision"] != "complete" or cpu != float(c["cpu_s"]):
                raise ValueError("Stage split disagrees with the paired receipt")
            stages = [float(c[k]) for k in ("launch_to_detections_s", "detections_to_terminal_s", "terminal_to_exit_s")]
            residency = float(c["initial_resident_page_fraction"])
        else:
            if r["decision"] == "complete":
                raise ValueError("Successful fix missing its stage split")
            stages, residency = [0., 0., total], None
        if not isclose(sum(stages), total, abs_tol=1e-6):
            raise ValueError("Stages disagree with external clock")
        rows.append(dict(case=r["case"], stages=stages, cpu_s=cpu, initial_residency=residency))
    if len(rows) != len({r["case"] for r in rows}) or len(rows) != 55:
        raise ValueError("Incomplete 55-recording comparison")
    return rows


def budget():
    rows = read_rows()
    scale = 25.661 / 60.966
    groups = {"all": rows, "warm": [r for r in rows if (r["initial_residency"] or 0.) > .95],
              "cold": [r for r in rows if r["initial_residency"] is not None and r["initial_residency"] < .2]}
    result = {}
    for g, group in groups.items():
        result[g] = dict(count=len(group), limits={o: threshold(group, scale, o) for o in ("scale_elapsed", "best", "worst")},
                         half_acquisition_gates={o: gates(group, .5, scale, o) for o in ("scale_elapsed", "best", "worst")})
    return dict(solver_cpu_scale=scale, groups=result, rows=rows)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.output.open("x") as out:
        json.dump(budget(), out, indent=2, allow_nan=False)
        out.write("\n")
