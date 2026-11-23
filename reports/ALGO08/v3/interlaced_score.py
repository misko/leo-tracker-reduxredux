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


def score(work, output, *, extra=False, checked=False):
    here = Path(__file__).resolve().parent / "measurements"
    complete_blob = (here / "sparse-consensus-summary.json.gz").read_bytes()
    paired_blob = (here / "paid-quadratic.json.gz").read_bytes()
    if (sha256(complete_blob).hexdigest() != "b843cfad5e324ad0c856019e3e607634a526f422520cc89e163bc3da6d58df73"
            or sha256(paired_blob).hexdigest() != "9237e3c1d1cbcca9b234dcb5782c1667857efe201683d84634e732004d2e40e1"):
        raise ValueError("Reference receipts differ from the frozen paired runs")
    complete, paired = (json.loads(gzip.decompress(b)) for b in (complete_blob, paired_blob))
    methods = ("causal_extra", "causal_extra_checked") if checked else ("causal_extra",) if extra else ("interlaced", "swapped")
    receipts = {c: {m: read(work / f"{c}-{m}.json") for m in methods} for c in CASES}
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
            base_count = data.get("base_lanes", data.get("paid_lanes"))
            if name != "complete" and (base_count != matched["identity"]["selection"]["paid_lanes"]
                                        or i["graph_parameters"] != matched["identity"]["graph_parameters"]):
                raise ValueError("Base lane count or graph policy differs")
            if name.startswith("causal_extra") and (data["extra_lanes"] + base_count != data["paid_lanes"]
                                                    or data["extra_lanes"] > data["lanes"] // 6):
                raise ValueError("Extra call budget exceeded")
            if name == "causal_extra_checked":
                unchecked = modes["causal_extra"]
                if (i["native_sha256"] != unchecked["identity"]["native_sha256"]
                        or not r["attempts"][0]["exterior"]["evaluated"]):
                    raise ValueError("Expected a matched packet and a completed regional decision")
            result = r["result"]
            science = section(result["arms"], truths[case], reference["result"]["arms"])
            deltas = [science["arms"][arm]["delta_error_km"] for arm in ARMS]
            passed = (result["status"] == "ok" and all(d is not None and d <= .25 for d in deltas)
                      if inside else result["status"] == "withheld")
            entry[name] = dict(status=result["status"], reason=result["reason"], selection=data,
                               charged=r["charged"], associated=result.get("associated", {}), passed=passed, **science)
            acquisition = i["ledger"]["acquisition_cpu_s"]
            if name != "complete":
                acquisition += data["paid_native_cpu_s"] - reference["identity"]["replay"]["all_native_cpu_s"]
                acquisition += data["selection_cpu_s"]
            entry[name]["projected_through_solve_cpu_s"] = acquisition + r["charged"]["cpu_s"]
        results[case] = entry
    full = gzip.compress(json.dumps(receipts, sort_keys=True, allow_nan=False).encode(), mtime=0)
    with output.with_suffix(".json.gz").open("xb") as f:
        f.write(full)
    write(output, dict(cases=results, full_sha256=sha256(full).hexdigest()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--extra", action="store_true")
    p.add_argument("--checked", action="store_true")
    a = p.parse_args()
    score(a.work, a.output, extra=a.extra, checked=a.checked)
