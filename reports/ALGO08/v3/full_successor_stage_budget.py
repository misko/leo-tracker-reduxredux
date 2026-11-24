"""Price the remaining single-core speed requirement on verified original-file pairs."""

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

from reports.ALGO08.v3.full_successor_score import paired_rows, roster


def elapsed_budget(installed, successor, acquisition, publication, detector):
    values = (installed, successor, acquisition, publication, detector)
    if any(not math.isfinite(n) or n <= 0 for n in values) or sum((acquisition, publication)) > successor:
        raise ValueError("Invalid disjoint wall-clock scopes")
    if detector > acquisition:
        raise ValueError("Receiver callbacks exceed the acquisition that contains them")
    gap = successor - installed / 2
    return dict(installed_s=installed, successor_s=successor, half_installed_s=installed/2, gap_s=gap,
                acquisition_s=acquisition, decision_and_publication_s=publication, native_detector_s=detector,
                remaining_s=successor-acquisition-publication,
                ratio_if_only_detector_instantaneous=installed/(successor-detector),
                minimum_savings_outside_detector_s=max(0, gap-detector),
                speedup_if_acquisition_and_publication_each_halved=installed/(successor-(acquisition+publication)/2),
                fraction_needed_from_acquisition_and_publication=max(0, gap)/(acquisition+publication))


def study(root, cases):
    assigned = roster()
    if not cases or not set(cases) <= assigned.keys() or len(set(cases)) != len(cases):
        raise ValueError("Expected distinct assigned recordings")
    row_bytes = (root / "rows.jsonl").read_bytes()
    rows = [json.loads(line) for line in row_bytes.splitlines()]
    selected = [r for r in rows if r["case"] in cases]
    pairs = paired_rows(selected, {k: assigned[k] for k in cases})
    records = []
    for installed, successor in pairs:
        case = installed["case"]
        source = next(r for r in selected if (r["case"], r["algorithm"]) == (case, "successor"))
        result = root / source["attempt"]
        if (not result.resolve(strict=True).is_relative_to((root / "cases" / case / "successor").resolve(strict=True)) or
                not source["verified_pair"] or source["outcome"] not in ("complete", "withheld")):
            raise ValueError("Expected a verified signed successor publication for this case")
        body = result.read_bytes()
        if "sha256:" + sha256(body).hexdigest() != source["attempt_result_sha256"]:
            raise ValueError("Benchmark result changed")
        witness = (result.parent / "publication/unified-short-bootstrap.json").read_bytes()
        actual = json.loads(witness)
        if (actual["native_sha256"] != json.loads(body)["native_sha256"] or
                actual["receiver_audit"]["recording_authority"] != successor["raw_authority_sha256"]):
            raise ValueError("Timing witness is for a different source or packet")
        phases = actual["phases"]
        callbacks = actual["receiver_audit"]["native"]["native_wall_ns"]
        cost = elapsed_budget(installed["elapsed_s"], successor["elapsed_s"],
                              phases["authenticated_raw_acquisition"]["elapsed_s"],
                              phases["decision_and_publication"]["elapsed_s"], sum(callbacks.values())/1e9)
        records.append(dict(case=case, decision=source["outcome"], attempt_sha256=source["attempt_result_sha256"],
                            witness_sha256=sha256(witness).hexdigest(), **cost))
    fields = ("installed_s", "successor_s", "acquisition_s", "decision_and_publication_s", "native_detector_s")
    return dict(cases=records, summed=elapsed_budget(*(sum(c[key] for c in records) for key in fields)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("cases", nargs="+")
    args = parser.parse_args()
    print(json.dumps(study(args.campaign, args.cases), indent=2, allow_nan=False))
