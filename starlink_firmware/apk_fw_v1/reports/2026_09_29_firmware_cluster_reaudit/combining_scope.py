"""Audit known-waveform combination and frozen early parity, without refitting."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
EXT = (BASE.parents[3] / "reports") / "2026_09_29_ds10_signal_extension/local/within-visit"


def cyclic_agreement(bits, parity):
    bits = np.asarray(bits, dtype=np.uint8)
    other = np.bitwise_xor.reduce(bits[:, 1:], axis=1)
    return np.array([np.mean((np.roll(bits[:, 0], shift) ^ other) == parity)
                     for shift in range(len(bits))])


def main():
    sources = []
    values = []
    for path in (EXT / "combined-parity.json", EXT / "receiver-combining/summary.json"):
        raw = path.read_bytes()
        values.append(json.loads(raw))
        sources.append(dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest()))
    parity, combining = values
    checked = []
    for row in parity["rows"]:
        scores = cyclic_agreement(row["signs"], row["parity"])
        gate = row["gates"][0]
        assert gate["quantile"] == 0 and gate["count"] == len(row["signs"])
        np.testing.assert_allclose([scores[0], scores[1:].mean(), scores[1:].max()],
                                   [gate["agreement"], gate["shifted_mean"], gate["shifted_max"]])
        rank = float(np.mean(scores >= scores[0] - 1e-12))
        checked.append(dict(**row, ungated_cyclic_rank=rank,
                            six_comparison_bonferroni_rank=min(1., rank * len(parity["rows"]))))
    for visit in combining["visits"]:
        for key in ("rx0", "rx1", "equal_average", "weighted"):
            r = visit[key]
            np.testing.assert_allclose(r["errors"] / r["count"], r["disagreement"])
        for r in visit["gates"] + visit["equal_gates"]:
            np.testing.assert_allclose(r["errors"] / r["count"], r["disagreement"])
    totals = {}
    for key in ("rx0", "rx1", "equal_average", "weighted"):
        errors = sum(v[key]["errors"] for v in combining["visits"])
        count = sum(v[key]["count"] for v in combining["visits"])
        totals[key] = dict(errors=errors, count=count, disagreement=errors / count)
    result = dict(parity=checked, combining=combining["visits"], totals=totals, sources=sources,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Saved signs and counts rechecked, no refit or fresh RF scan. "
                  "Parity ranks only for ungated frames; confidence-gated controls do not "
                  "preserve donor eligibility. Six-comparison correction excludes historical "
                  "selection. Late known-sequence disagreement is not early-header BER.")
    (BASE / "local/combining-scope.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Known waveform", totals)
    print("Ungated parity", [(r["visit"], r["mode"], r["ungated_cyclic_rank"])
                             for r in checked])
    print("Gated support", [r["gates"][1:][0]["count"] for r in checked])


if __name__ == "__main__":
    main()
