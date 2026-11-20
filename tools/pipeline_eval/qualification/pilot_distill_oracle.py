"""Replay oracle-only inputs with the compact solver's positive margin domain."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import sleep

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..variants.pilot_distill import MARGIN
from . import pilot_distill_trial as trial
from .full_v5_check import _sha
from .phase_support_results import pack

REPORT = trial.REPORT


def solver_eligible(members, probes):
    return {i: j for i, j in members if probes[i]["candidates"][j][MARGIN] > 0}


def amend(work, original, report=REPORT):
    if (report / "oracle-amendment-lock.json").is_file():
        raise FileExistsError("pilot oracle amendment already ran")
    plan_file = report / "replay-plan.json"
    plan = whole_iq.read(plan_file)
    bundle = original / "compact-cut"
    if whole_iq.receiver_identity(bundle) != plan["installed"]:
        raise ValueError("oracle amendment changed the compact receiver")
    work.mkdir()
    affected, bindings = {}, {}
    for ident, case in plan["cases"].items():
        entry = case["inputs"]["oracle"]
        packet = whole_iq.read(whole_iq.checked(Path(entry["path"]), entry["sha256"]))
        native = whole_iq.checked(Path(packet["fast"]["local"]), packet["fast"]["native_sha256"])
        probes = json.loads(native.read_bytes())["source"]["probes"]
        original_members = packet["oracle_members"]
        valid = solver_eligible(original_members, probes)
        if len(valid) == len(original_members):
            continue
        missing = sorted(set(map(tuple, original_members)) - set(valid.items()))
        bindings[ident] = dict(
            removed=[(i, j, probes[i]["candidates"][j][MARGIN]) for i, j in missing],
            eligible=len(valid),
            original=len(original_members),
        )
        packet.update(
            oracle_members=sorted(valid.items()),
            counts={"oracle": len(valid)},
            selection_sha256={"oracle": trial.chosen_digest(valid)},
        )
        new = work / ident / "oracle.json"
        save_json(new, packet)
        trial_case = dict(case, inputs={"oracle": dict(path=str(new), sha256=_sha(new))})
        affected[ident] = trial_case
        bindings[ident]["input_sha256"] = _sha(new)
    amendment_path = report / "oracle-amendment-plan.json"
    save_json(
        amendment_path,
        dict(
            cases=bindings,
            source_sha256=_sha(Path(__file__)),
            explanation_sha256=_sha(REPORT / "ORACLE-AMENDMENT.md"),
            original_plan_sha256=_sha(plan_file),
        ),
    )

    def run(item):
        ident, case = item
        cpu = case["cpu"]
        prior = [
            original / owner / arm / "receipt.json"
            for owner, lane in plan["cases"].items()
            if lane["cpu"] == cpu
            for arm in lane["order"]
        ]
        # The amended fit starts after the last original fit on this core.
        for _ in range((trial.LIMIT + 15) * len(prior) // 5 + 1):
            if all(path.exists() for path in prior):
                row = trial.run_one(work, bundle, case, "oracle", cpu)
                return dict(row, original_oracle_excluded=len(bindings[ident]["removed"]))
            sleep(5)
        raise TimeoutError(f"original CPU lane {cpu} did not return all scheduled fits")

    with ThreadPoolExecutor(len(affected)) as pool:
        rows = list(pool.map(run, affected.items()))
    measured = report / "oracle-amendment.jsonl.gz"
    pack(measured, rows)
    save_json(
        report / "oracle-amendment-lock.json",
        dict(cases=list(affected), files={p.name: _sha(p) for p in (measured, amendment_path)}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=local_output)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--report", type=local_output, default=REPORT)
    args = parser.parse_args()
    amend(args.work, args.original, args.report)
