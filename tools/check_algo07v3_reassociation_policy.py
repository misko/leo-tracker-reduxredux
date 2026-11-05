"""External exact final-policy oracle, including deliberately invalid admissions."""

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint


def run(args):
    bindings = {}
    cases = []
    for path in args.case:
        raw = path.read_bytes()
        bindings[str(path)] = hashlib.sha256(raw).hexdigest()
        cases.append(json.loads(raw))
    if args.side == "reference":
        path = args.runtime / "tools/algo07_science/policy.py"
        spec = importlib.util.spec_from_file_location("frozen_reassociation_policy", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from leo.analysis.localization_v3 import reassociation_policy as module

        path = Path(module.__file__)
    results = []
    for case in cases:
        mutations = (
            ("unchanged", "phase", "evidence", "folds", "gain")
            if case["records"]
            else ("unchanged",)
        )
        for mutation in mutations:
            records, guards = copy.deepcopy(case["records"]), copy.deepcopy(case["guards"])
            if mutation != "unchanged":
                row = records[0]
                if mutation == "phase":
                    row["pair"]["fitted_c"]["phase_closed"] = False
                elif mutation == "evidence":
                    row["pair"]["c0"]["native_ids_sha256"] = "deliberately-unmatched"
                elif mutation == "folds":
                    guards[row["name"]]["unique_folds"] = 4
                else:
                    row["gains"]["c0"] = 0.0
            results.append(
                dict(mutation=mutation, result=module.select(case["baseline"], records, guards))
            )
    args.output.write_text(json.dumps(fingerprint(results), sort_keys=True, allow_nan=False) + "\n")

    def binding(file):
        return dict(path=str(file), sha256=hashlib.sha256(Path(file).read_bytes()).hexdigest())

    receipt = dict(
        side=args.side,
        inputs=bindings,
        policy=binding(path),
        tool=binding(__file__),
        output=binding(args.output),
        decisions=len(results),
        full_pipeline_parity=False,
    )
    args.output.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(dict(side=args.side, decisions=len(results), output=receipt["output"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=("reference", "candidate"), required=True)
    parser.add_argument("--case", action="append", required=True, type=Path)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Policy comparison output exists")
    run(args)
