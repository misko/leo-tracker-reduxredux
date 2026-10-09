"""Fresh production B7 fits against sealed iteration85; archived grid inputs explicit."""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "2026_10_09_position_error_iter85"))
from dependencies import load, read  # noqa: E402

from leo.application.hard60_b7 import run_joint_stages  # noqa: E402
from leo.application.regional_position_runner import json_value  # noqa: E402


def region(document):
    finals = []
    for arm in document["methods"][0]["arms"]:
        chosen = arm["selected"]
        if chosen is None:
            continue
        row = next(
            r
            for r in document["diagnostics"]["final_starts"]
            if r["arm"] == arm["name"]
            and r["basin"] == chosen["source_basin"]
            and r["fit"]
            and r["fit"]["converged"]
            and abs(r["fit"]["objective"] - chosen["objective"]) < 1e-9
        )
        finals.append(
            dict(
                row,
                satellites=chosen["satellites"],
                association=dict(final=dict(assigned=chosen["associated_windows"])),
            )
        )
    return dict(finals=finals, calibrations=document["diagnostics"]["calibrations"])


def evaluate(binding):
    label = binding["member"]["inventory_label"]
    destination = HERE / "qualification" / f"{label}.json"
    if destination.exists():
        return
    start = time.monotonic()
    case, baseline, _ = load(binding["loader_binding"])
    documents = dict(baseline=baseline)
    documents.update({k: read(ROOT / p) for k, p in binding["regions"].items()})
    regions = {k: region(v) for k, v in documents.items()}

    def stage(key, budget, operation):
        try:
            return dict(result=json_value(operation()), reason=None)
        except (ValueError, TimeoutError) as error:
            return dict(result=None, reason=repr(error))

    operational, attempts, reasons = run_joint_stages(
        case.prepared.observations, case.bank, case.prior, regions, stage
    )
    expected = read(HERE.parent / "2026_10_09_position_error_iter85/results" / f"{label}.json")
    comparisons = {}
    for arm, actual in operational.items():
        before, after = expected["stages"]["B7"][arm], actual["fit"]
        position_delta_m = float(
            np.linalg.norm(np.asarray(before["vector"][:2]) - after["vector"][:2]) * 1000
        )
        score_delta = after["objective"] - before["objective"]
        passed = (
            position_delta_m <= 1
            and abs(score_delta) <= 0.001
            and actual["accepted_stage"] == before["stage"]
            and after["converged"] == before["converged"]
        )
        comparisons[arm] = dict(
            passed=passed,
            position_delta_m=position_delta_m,
            objective_delta=score_delta,
            accepted_stage=actual["accepted_stage"],
        )
    payload = dict(
        member=binding["member"],
        comparisons=comparisons,
        operational=operational,
        attempts=attempts,
        reasons=reasons,
        elapsed_s=time.monotonic() - start,
        scope="Fresh production downstream fits; immutable archived regional search",
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(json_value(payload), indent=2) + "\n")
    print(label, comparisons, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--labels", nargs="*")
    args = parser.parse_args()
    members = read(HERE.parent / "2026_10_09_position_error_iter85/protocol.json")["members"]
    for index, binding in enumerate(members):
        if index % args.shards == args.shard and (
            not args.labels or binding["member"]["inventory_label"] in args.labels
        ):
            evaluate(binding)
