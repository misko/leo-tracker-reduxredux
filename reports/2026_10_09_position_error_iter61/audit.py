"""Frozen ordinary-start gradient and evaluation-cost audit; no optimization."""

import hashlib
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from native_joint import SmoothJointObjective as NativeJointObjective

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_10_09_position_error_iter58"))
from smooth_joint import SmoothJointObjective  # noqa: E402

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import (  # noqa: E402
    HARD60_SCORE,
    Hard60Objective,
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
    hard, smooth = SmoothJointObjective(*args), NativeJointObjective(*args)
    seen, rows = set(), []
    for index, source in enumerate(census["rows"]):
        if source["status"] != "feasible" or source["region"] in seen:
            continue
        seen.add(source["region"])
        vector, clock = np.asarray(source["seed"]), np.asarray(source["clock"])
        costs, results = {}, {}
        for name, model in (("numpy", hard), ("native", smooth)):
            times = []
            for _ in range(3):
                start = time.perf_counter()
                result = model.evaluate_joint(vector, clock)
                times.append(time.perf_counter() - start)
            costs[name] = float(np.median(times))
            results[name] = result
        differences = {}
        for component, position in [("objective", 0), ("gradient", 1), ("clock_gradient", 2)]:
            a, b = results["numpy"][position], results["native"][position]
            np.testing.assert_allclose(a, b, rtol=1e-9, atol=1e-7)
            differences[component] = float(np.max(np.abs(np.asarray(a) - np.asarray(b))))
        np.testing.assert_allclose(
            results["numpy"][3].responsibilities,
            results["native"][3].responsibilities,
            atol=1e-10,
            rtol=1e-9,
        )
        rows.append(
            dict(
                index=index,
                region=source["region"],
                evaluation_seconds=costs,
                differences=differences,
            )
        )
        print(index, source["region"], costs, flush=True)
        write_json(HERE / "progress.json", dict(rows=rows))
    write_json(HERE / "results.json", dict(rows=rows, scope=protocol["scope"]))


if __name__ == "__main__":
    main()
