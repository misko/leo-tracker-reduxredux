"""Frozen ordinary-start gradient and evaluation-cost audit; no optimization."""

import hashlib
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_10_09_position_error_iter58"))
from smooth_joint import SmoothJointObjective  # noqa: E402

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import (  # noqa: E402
    HARD60_SCORE,
    Hard60Objective,
    InitialClockObjective,
    load_member,
    read,
    write_json,
)


def main():
    protocol = read(HERE / "protocol.json")
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    if (HERE / "results.json").exists():
        raise FileExistsError("Preserve original audit")
    census = read(REPORTS / "2026_10_09_position_error_iter53/results.json")
    members = read(REPORTS / "2026_10_08_position_error_iter29/protocol.json")["members"]
    case = load_member(next(m for m in members if m["label"] == "RESERVED-001"))
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in census["candidate_union"]])
    doc = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
    selected = next(a["selected"] for a in doc["methods"][0]["arms"] if a["name"] == "fitted-c")
    cal = doc["diagnostics"]["calibrations"][selected["source_basin"]]
    base = Hard60Objective(
        case.prepared.observations,
        bank,
        case.prior,
        replace(HARD60_SCORE, relative_sigma_s=1),
        receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
    )
    args = (base, cal["correction"]["nodes_s"], cal["correction"]["knots_hz"], 2)
    hard, smooth = InitialClockObjective(*args), SmoothJointObjective(*args)
    seen, rows = set(), []
    for index, source in enumerate(census["rows"]):
        if source["status"] != "feasible" or source["region"] in seen:
            continue
        seen.add(source["region"])
        vector, clock = np.asarray(source["seed"]), np.asarray(source["clock"])
        costs = {}
        for name, model in (("hard", hard), ("smooth", smooth)):
            times = []
            for _ in range(3):
                start = time.perf_counter()
                result = model.evaluate_joint(vector, clock)
                times.append(time.perf_counter() - start)
            costs[name] = float(np.median(times))
        value, gradient, clock_gradient, _ = result
        checks = []
        directions = [("vector", i) for i in (0, 1, 3, 5, 6, 7, 8)] + [("clock", 0)]
        for kind, coord, scale in [(k, c, s) for k, c in directions for s in (0.1, 0.01)]:
            values = vector if kind == "vector" else clock
            step = (0.0001 if kind == "vector" and coord >= 7 else 0.001) * scale
            original = values[coord]
            values[coord] = original + step
            plus = smooth.evaluate_joint(vector, clock)[0]
            values[coord] = original - step
            minus = smooth.evaluate_joint(vector, clock)[0]
            values[coord] = original
            finite = (plus - minus) / (2 * step)
            analytic = float((gradient if kind == "vector" else clock_gradient)[coord])
            checks.append(
                dict(
                    kind=kind,
                    coordinate=coord,
                    step=step,
                    analytic=analytic,
                    finite_difference=finite,
                    absolute_difference=abs(finite - analytic),
                )
            )
        rows.append(
            dict(
                index=index,
                region=source["region"],
                objective=value,
                evaluation_seconds=costs,
                checks=checks,
            )
        )
        print(index, source["region"], max(r["absolute_difference"] for r in checks), flush=True)
        write_json(HERE / "progress.json", dict(rows=rows))
    write_json(HERE / "results.json", dict(rows=rows, scope=protocol["scope"]))


if __name__ == "__main__":
    main()
