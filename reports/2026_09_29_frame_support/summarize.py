"""Verify past-only envelopes and account for every abstention."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent


def main():
    d = json.loads((BASE / "results.json").read_text())
    for path, expected in d["input_sha256"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    assert len(d["rows"]) == 800 and len(d["groups"]) == 16
    for g in d["groups"]:
        scores = np.array(g["control_scores"])
        assert scores.shape == (30, 3)
        assert float(scores.max()) == g["threshold"]
        for r in [
            r for r in d["rows"] if (r["signal"], r["receiver"]) == (g["signal"], g["receiver"])
        ]:
            accepted = r["exact_score"] > g["threshold"]
            assert accepted == r["support"]["accepted"]
            assert r["support"]["nmse"] == (r["baseline_nmse"] if accepted else 1)
            assert (r["support"]["frequency_hz"] is not None) == accepted
    names = list(dict.fromkeys(r["signal"] for r in d["rows"]))
    assert {(r["signal"], r["receiver"], r["frame"]) for r in d["rows"]} == {
        (n, rx, f) for n in names for rx in [0, 1] for f in range(30, 80)
    }
    summary = []
    for name in names:
        s = [r for r in d["rows"] if r["signal"] == name]
        a = np.array([r["baseline_nmse"] for r in s])
        b = np.array([r["support"]["nmse"] for r in s])
        c = np.array([r["fixed"]["nmse"] for r in s])
        summary.append(
            dict(
                signal=name,
                count=len(s),
                accepted=sum(r["support"]["accepted"] for r in s),
                fixed_accepted=sum(r["fixed"]["accepted"] for r in s),
                wrong_accepted=sum(r["wrong_accepted"] for r in s),
                improved=int(sum(b < a)),
                worsened=int(sum(b > a)),
                unchanged=int(sum(b == a)),
                mean_paired_gain=float(np.mean(a - b)),
                median_paired_gain=float(np.median(a - b)),
                fixed_mean_paired_gain=float(np.mean(a - c)),
            )
        )
    (BASE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("All envelopes, membership, bindings and 800 predictions verified.")
    print("mean gain", sum(r["mean_paired_gain"] * r["count"] for r in summary) / 800)


if __name__ == "__main__":
    main()
