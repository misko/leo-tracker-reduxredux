"""Descriptive discovery-to-evaluation signs in quality-qualified matched visits."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
OUT = BASE / "local/simultaneous5"


def agreement_matrix(arrays):
    return [[float((a[0] == b[1:]).mean()) for b in arrays] for a in arrays]


def main():
    audit_path = OUT / "audit.json"
    audit = json.loads(audit_path.read_text())
    results = []
    for pair in audit["pairs"]:
        receipt = OUT / f"pair-{pair['pair']}/recovery.json"
        digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
        assert digest == audit["source_sha256"][str(receipt)]
        recovered = json.loads(receipt.read_text())["rows"]
        for visit in pair["visits"]:
            if not visit["usable"]:
                continue
            rows = [r for r in recovered if r["visit"] == visit["visit"]]
            arrays, support = [], None
            for r in rows:
                path = Path(r["artifact"])
                assert hashlib.sha256(path.read_bytes()).hexdigest() == r["artifact_sha256"]
                with np.load(path) as d:
                    bins = d["bins"].copy()
                    pilots = json.loads(str(d["metadata"]))["pilot_bins"]
                    nonpilot = bins[~np.isin(bins, pilots)]
                    support = nonpilot if support is None else np.intersect1d(support, nonpilot)
                    arrays.append((bins, d["z"][r["qualified"], :6].real >= 0))
            signs = [z[:, :, np.searchsorted(bins, support)] for bins, z in arrays]
            matrix = agreement_matrix(signs)
            results.append(dict(pair=pair["pair"], visit=visit["visit"], bins=support.tolist(),
                ids=[r["id"] for r in rows], frames=[r["qualified"] for r in rows],
                observations_per_frame=int(signs[0].shape[1] * signs[0].shape[2]),
                agreement=matrix,
                within_minus_cross=float((matrix[0][0] + matrix[1][1]
                                          - matrix[0][1] - matrix[1][0]) / 2)))
    result = dict(visits=results, source_sha256=hashlib.sha256(audit_path.read_bytes()).hexdigest(),
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="First qualified frame is donor; remaining frames evaluate. Raw "
                  "sign agreement includes shared constants. One paired visit cannot establish "
                  "identity persistence, satellite truth, or independent receiver consensus.")
    (OUT / "signs.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
