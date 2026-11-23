"""Bind paid-graph comparisons to the matched complete archived controls."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_score import PHYSICAL, references
from aperture_trial import ARMS, read, write
from mixture_score import section
from sparse_consensus_trial import CASES
from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km


def score(work, output, *, include_quadratic=False):
    controls = Path(__file__).resolve().parent / "measurements/sparse-consensus-summary.json.gz"
    raw = controls.read_bytes()
    if sha256(raw).hexdigest() != "b843cfad5e324ad0c856019e3e607634a526f422520cc89e163bc3da6d58df73":
        raise ValueError("Complete control receipts changed")
    baseline = json.loads(gzip.decompress(raw))
    requested = ("margin", "graph", "quadratic") if include_quadratic else ("margin", "graph")
    receipts = {case: {arm: read(work / f"{case}-{arm}.json") for arm in requested} for case in CASES}
    truths = references()
    physical, = [r for r in read(PHYSICAL)["cases"] if r["dataset_label"] == CASES[0] and r["authority_eligible"]]
    truths[CASES[0]] = [physical["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    result = {}
    for case, modes in receipts.items():
        control = baseline[case]["complete"]
        reference = control["result"]["arms"]
        entry = {"complete": dict(status=control["result"]["status"], charged=control["charged"],
                                  **section(reference, truths[case], reference))}
        inside = face_clearance_km(control["identity"]["offer"], truths[case]) >= 0
        for mode, receipt in modes.items():
            identity = receipt["identity"]
            keys = ("case", "offer", "archive", "source", "ledger")
            if any(identity[k] != control["identity"][k] for k in keys):
                raise ValueError("Input, authority, causal archive or region differs")
            if identity["selection"]["mask_sha256"] != control["identity"]["replay"]["mask_sha256"]:
                raise ValueError("Compared selectors did not pay for identical visits")
            if mode == "quadratic" and identity["native_sha256"] != modes["margin"]["identity"]["native_sha256"]:
                raise ValueError("Quadratic fit used a different receiver packet")
            if receipt.get("reused_solver_sha256"):
                if (receipt["reused_solver_sha256"] != sha256((work / f"{case}-margin.json").read_bytes()).hexdigest()
                        or receipt["result"] != modes["margin"]["result"]
                        or identity["native_sha256"] != modes["margin"]["identity"]["native_sha256"]):
                    raise ValueError("Reused result differs from measured solver input")
            resolved = receipt["result"]
            arm_scores = section(resolved["arms"], truths[case], reference)
            deltas = [arm_scores["arms"][arm]["delta_error_km"] for arm in ARMS]
            passed = (resolved["status"] == "ok" and all(d is not None and d <= .25 for d in deltas)
                      if inside else resolved["status"] == "withheld")
            entry[mode] = dict(status=resolved["status"], reason=resolved["reason"], passed=passed,
                               selection=identity["selection"], charged=receipt["charged"],
                               associated=resolved.get("associated"), **arm_scores)
        result[case] = entry
    payload = gzip.compress(json.dumps(receipts, allow_nan=False, sort_keys=True).encode(), mtime=0)
    with output.with_suffix(".json.gz").open("xb") as f:
        f.write(payload)
    write(output, dict(cases=result, receipt_sha256=sha256(payload).hexdigest(), control_sha256=sha256(raw).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--include-quadratic", action="store_true")
    args = parser.parse_args()
    score(args.work, args.output, include_quadratic=args.include_quadratic)
