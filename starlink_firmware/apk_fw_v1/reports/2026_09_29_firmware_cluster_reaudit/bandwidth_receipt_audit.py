"""Recompute carrier reliability and audit wide-feature transfer support."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
SOURCE = (BASE.parents[3] / "reports") / "2026_09_29_identity_resumption/local"


def disagreement(rows, indices):
    errors = np.array([r["errors"] for r in rows])[:, indices].sum()
    counts = np.array([r["count"] for r in rows])[:, indices].sum()
    if not counts:
        raise ValueError("No decisions")
    return float(errors / counts)


def main():
    paths = [SOURCE / name for name in ("bandwidth-extension/summary.json",
                                       "carrier-reliability.json", "lower-profile-transfer.json")]
    wide, reliability, profiles = [json.loads(p.read_text()) for p in paths]
    edges = []
    for edge in reliability["edges"]:
        rows = [r for r in reliability["frames"] if r["edge"] == edge["edge"] and r["half"] == 1]
        bins = edge["bins"]
        core = [526, 527, 536, 537] if edge["edge"] == "lower" else [486, 487, 496, 497]
        core_ix = [i for i, b in enumerate(bins) if b in core]
        extra_ix = [i for i, b in enumerate(bins) if b not in core]
        a, b = [disagreement(rows, ix) for ix in (core_ix, extra_ix)]
        assert abs(a - edge["core_held_error"]) < 1e-12
        assert abs(b - edge["extra_held_error"]) < 1e-12
        edges.append(dict(original=edge, held_frames=len(rows), core=a, extra=b,
                          extra_minus_core=b - a))
    supported = [e for e in wide["experiments"] if e.get("matched_same_pairs", 0)]
    assert len(supported) == 1
    experiment = supported[0]
    assert len(experiment["matched_pairs"]) == experiment["matched_same_pairs"] == 14
    assert not any(p["cross_session"] for p in experiment["matched_pairs"])
    for row in profiles["comparisons"]:
        corrected = min(1., len(profiles["comparisons"]) * row["circular_p"])
        assert abs(row["family_p"] - corrected) < 1e-12
    output = dict(bandwidth=wide, reliability=edges, lower_profile_transfer=profiles,
                  source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Existing receipts independently aggregated, no repeated feature "
                  "scan. Tail model disagreement is not true message BER. Wider-carrier "
                  "identity support is within session only; profile nontransfer does not "
                  "prove absence of changing or scrambled message content.")
    (BASE / "local/bandwidth-receipt-audit.json").write_text(json.dumps(output, indent=2) + "\n")
    for r in edges:
        print(r["original"]["edge"], r["held_frames"], r["core"], r["extra"])
    print("Wide matched pairs", experiment["matched_same_pairs"], "cross-session", 0,
          "profile comparisons", len(profiles["comparisons"]))


if __name__ == "__main__":
    main()
