"""Reconcile every block and frame before reporting support ablations."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent


def main():
    d = json.loads((BASE / "results.json").read_text())
    for path, expected in d["input_sha256"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    blocks = d["blocks"]
    names = list(dict.fromkeys(b["signal"] for b in blocks))
    assert len(blocks) == 80 and len(names) == 8
    assert {(b["signal"], b["receiver"], b["first_frame"]) for b in blocks} == {
        (n, rx, f) for n in names for rx in [0, 1] for f in range(30, 80, 10)
    }
    for b in blocks:
        assert len(b["rows"]) == 10
        assert sum(r["accepted"] for r in b["rows"]) == b["retained"]
        for r in b["rows"]:
            assert r["abstention_nmse"] == (r["support_fit_nmse"] if r["accepted"] else 1)
        if b["retained"] == 10:
            assert b["all_frequency_hz"] == b["support_frequency_hz"]
    summary = []
    for name in names:
        selected = [b for b in blocks if b["signal"] == name]
        rows = [r for b in selected for r in b["rows"]]
        a = np.array([r["all_nmse"] for r in rows])
        b = np.array([r["support_fit_nmse"] for r in rows])
        c = np.array([r["abstention_nmse"] for r in rows])
        delta = [
            x["support_frequency_hz"] - x["all_frequency_hz"]
            for x in selected
            if x["support_frequency_hz"] is not None
        ]
        summary.append(
            dict(
                signal=name,
                blocks=len(selected),
                retained_frames=sum(x["retained"] for x in selected),
                max_abs_frequency_change_hz=max(abs(np.array(delta))),
                mean_frequency_weighting_gain=float(np.mean(a - b)),
                mean_with_abstention_gain=float(np.mean(a - c)),
                frequency_weighting_wins=int(sum(b < a)),
                abstention_wins=int(sum(c < a)),
                abstention_losses=int(sum(c > a)),
            )
        )
    (BASE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("Verified 80 blocks, 800 scored frames, inherited support and source hashes.")


if __name__ == "__main__":
    main()
