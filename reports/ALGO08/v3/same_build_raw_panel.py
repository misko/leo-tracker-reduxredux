"""Combine verified whole-recording receipts from one frozen single-core implementation."""

import argparse
import gzip
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from statistics import median


ARMS = ("c0", "fitted_c")
MODES = ("stock", "candidate")
IMPLEMENTATION = ("stock", "route_flags", "library_sha256", "sources", "host")


def implementation(admission):
    identity = {key: admission[key] for key in IMPLEMENTATION}
    receiver = admission.get("receiver_configuration")
    if receiver is not None:
        recipe = json.dumps(receiver["recipe"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if receiver["detector_recipe_sha256"] != "sha256:"+sha256(recipe.encode()).hexdigest():
            raise ValueError("Receiver configuration does not bind its detector recipe")
        identity["receiver_configuration"] = receiver
    return identity


def read_pair(receipt):
    admission = receipt["admission"]
    modes = receipt["original"]
    if modes["stock"]["opportunities"] != modes["candidate"]["opportunities"]:
        raise ValueError("Implementations received different radio opportunities")
    order = sorted(MODES, key=lambda m: modes[m]["process"]["clock"]["started_unix_ns"])
    if order != admission["order"] or not receipt["pre_score_sha256"]:
        raise ValueError("Missing or inconsistent enrollment and launch provenance")
    row = dict(case=admission["case"], raw_authority=admission["raw_authority"], visits=admission["issued"],
               order=order, runs={})
    for mode in MODES:
        run = modes[mode]
        clock = run["process"]["clock"]
        elapsed = clock["elapsed_s"]
        if (clock["exit_code"] != 0 or not isfinite(elapsed) or elapsed <= 0
                or run["science"]["raw_authority"] != row["raw_authority"]):
            raise ValueError("Invalid process clock or unmatched original recording")
        receiver = admission.get("receiver_configuration")
        if receiver is not None and mode == "candidate" and run["bootstrap"]["detector_recipe_sha256"] != receiver["detector_recipe_sha256"]:
            raise ValueError("Candidate packet uses a different enrolled receiver configuration")
        times = run["time_boundaries"]
        detection, terminal = times["detections_file_s"], times["terminal_file_s"]
        if not 0 <= detection <= terminal <= elapsed or times["exit_s"] != elapsed:
            raise ValueError("Published evidence is outside the measured process boundaries")
        decision = run["science"]["receipt"]["decision"]
        if decision not in ("complete", "withheld") or len(run["figures"]) != (8 if decision == "complete" else 0):
            raise ValueError("Incomplete scientific or media verification")
        errors = {}
        if decision == "complete":
            errors = receipt["geographic"]["runs"][mode]["horizontal_error_km"]
            if set(errors) != set(ARMS) or any(not isfinite(v) or v < 0 for v in errors.values()):
                raise ValueError("Missing or invalid horizontal error on published fix")
        row["runs"][mode] = dict(elapsed_s=elapsed, cpu_s=clock["cpu_s"], decision=decision, errors_km=errors,
                                stages_s=[detection, terminal-detection, elapsed-terminal])
    return row


def summarize(receipts):
    if not receipts:
        raise ValueError("No matched pairs supplied")
    identity = implementation(receipts[0]["admission"])
    if any(implementation(r["admission"]) != identity for r in receipts):
        raise ValueError("Raw pairs use different receiver configurations, flags, pinned sources, libraries, release or host settings")
    rows = sorted((read_pair(r) for r in receipts), key=lambda r: (r["visits"], r["case"]))
    if any(len({r[k] for r in rows}) != len(rows) for k in ("case", "raw_authority")):
        raise ValueError("A recording was enrolled more than once")
    total = {m: sum(r["runs"][m]["elapsed_s"] for r in rows) for m in MODES}
    paired = [r["runs"]["candidate"]["elapsed_s"] / r["runs"]["stock"]["elapsed_s"] for r in rows]
    fingerprint = sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return dict(implementation_sha256=fingerprint, rows=rows, total_s=total,
                median_paired_ratio=median(paired), summed_ratio=total["candidate"]/total["stock"],
                fix_counts={m: sum(r["runs"][m]["decision"] == "complete" for r in rows) for m in MODES})


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("receipts", type=Path, nargs="+")
    args = cli.parse_args()
    inputs = [p.read_bytes() for p in args.receipts]
    result = summarize([json.loads(gzip.decompress(b)) for b in inputs])
    result["source_receipt_sha256"] = {p.name: sha256(b).hexdigest() for p, b in zip(args.receipts, inputs, strict=True)}
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
