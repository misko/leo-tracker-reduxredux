"""Score the six frozen receipts after all three matched comparisons finish."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_score import PHYSICAL, references
from aperture_trial import read, write
from mixture_score import section
from sparse_consensus_trial import CASES, MODES
from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km


def score(directory):
    receipts = {case: {mode: read(directory / f"{case}-{mode}.json") for mode in MODES} for case in CASES}
    truths = references()
    physical, = [r for r in read(PHYSICAL)["cases"] if r["dataset_label"] == CASES[0] and r["authority_eligible"]]
    point = physical["reference"]
    truths[CASES[0]] = (point["latitude_deg"], point["longitude_deg"])
    summary = {}
    for case, arms in receipts.items():
        base, sparse = (arms[k] for k in MODES)
        for key in ("archive", "ledger", "offer", "source"):
            if base["identity"][key] != sparse["identity"][key]:
                raise ValueError(f"{case} {key} differs")
        truth = truths[case]
        clearance = face_clearance_km(base["identity"]["offer"], truth)
        if (clearance < 0) != case.endswith("-far"):
            raise ValueError("Offer and scoring reference disagree")
        scores = {}
        for mode, receipt in arms.items():
            result = receipt["result"]
            scores[mode] = dict(status=result["status"], reason=result["reason"], clocks=receipt["charged"],
                                associated=result.get("associated", {}), **section(result["arms"], truth, base["result"]["arms"]))
        comparison = scores["buffered"]["arms"]
        retained = all(scores[mode]["status"] == "ok" for mode in MODES)
        within = (retained and all(comparison[k]["error_km"] <= scores["complete"]["arms"][k]["error_km"] + .25
                                   for k in comparison) if clearance >= 0
                  else all(scores[mode]["status"] == "withheld" for mode in MODES))
        summary[case] = dict(offer_clearance_km=clearance, passed=within, results=scores,
                             replay=sparse["identity"]["replay"], acquisition_cpu_s=sparse["identity"]["ledger"]["acquisition_cpu_s"])
    return summary, receipts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    summary, receipts = score(args.directory)
    data = gzip.compress(json.dumps(receipts, sort_keys=True, allow_nan=False).encode(), mtime=0)
    with args.output.with_suffix(".json.gz").open("xb") as f:
        f.write(data)
    write(args.output, dict(cases=summary, receipts_sha256=sha256(data).hexdigest()))
