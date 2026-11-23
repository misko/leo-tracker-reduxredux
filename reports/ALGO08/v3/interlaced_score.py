"""Verify the equal-cost and geographical comparisons before scoring staggered timings."""

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


def score(work, output):
    here = Path(__file__).resolve().parent / "measurements"
    complete_blob = (here / "sparse-consensus-summary.json.gz").read_bytes()
    paired_blob = (here / "paid-quadratic.json.gz").read_bytes()
    if (sha256(complete_blob).hexdigest() != "b843cfad5e324ad0c856019e3e607634a526f422520cc89e163bc3da6d58df73"
            or sha256(paired_blob).hexdigest() != "9237e3c1d1cbcca9b234dcb5782c1667857efe201683d84634e732004d2e40e1"):
        raise ValueError("Reference receipts differ from the frozen paired runs")
    complete, paired = (json.loads(gzip.decompress(b)) for b in (complete_blob, paired_blob))
    receipts = {c: {m: read(work / f"{c}-{m}.json") for m in ("interlaced", "swapped")} for c in CASES}
    truths = references()
    phys, = [r for r in read(PHYSICAL)["cases"] if r["dataset_label"] == CASES[0] and r["authority_eligible"]]
    truths[CASES[0]] = tuple(phys["reference"][k] for k in ("latitude_deg", "longitude_deg"))
    results = {}
    for case in CASES:
        matched, reference = paired[case]["quadratic"], complete[case]["complete"]
        modes = dict(complete=reference, simultaneous=matched, **receipts[case])
        entry = {}
        inside = face_clearance_km(matched["identity"]["offer"], truths[case]) >= 0
        for name, r in modes.items():
            i = r["identity"]
            if any(i[k] != reference["identity"][k] for k in ("source","archive","offer","ledger")):
                raise ValueError("Unmatched recording, offer or archive")
            data = i.get("selection", {})
            if name != "complete" and (data["paid_lanes"] != matched["identity"]["selection"]["paid_lanes"]
                                        or i["graph_parameters"] != matched["identity"]["graph_parameters"]):
                raise ValueError("Paid count or graph policy differs")
            result = r["result"]
            science = section(result["arms"], truths[case], reference["result"]["arms"])
            deltas = [science["arms"][arm]["delta_error_km"] for arm in ARMS]
            passed = (result["status"] == "ok" and all(d is not None and d <= .25 for d in deltas)
                      if inside else result["status"] == "withheld")
            entry[name] = dict(status=result["status"], reason=result["reason"], selection=data,
                               charged=r["charged"], associated=result.get("associated", {}), passed=passed, **science)
        results[case] = entry
    full = gzip.compress(json.dumps(receipts, sort_keys=True, allow_nan=False).encode(), mtime=0)
    with output.with_suffix(".json.gz").open("xb") as f:
        f.write(full)
    write(output, dict(cases=results, full_sha256=sha256(full).hexdigest()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    score(a.work, a.output)
