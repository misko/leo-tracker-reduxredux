"""Verify timing trials and aggregate all selected frames without exclusions."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent


def main():
    d = json.loads((BASE / "results.json").read_text())
    for path, expected in d["input_sha256"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    assert len(d["rows"]) == 32
    summary = []
    for signal in ["S31", "S32"]:
        for rx in [0, 1]:
            allrows = [r for r in d["rows"] if r["signal"] == signal and r["receiver"] == rx]
            assert len(allrows) == 8 and len({r["frame"] for r in allrows}) == 8
            groups = {}
            for weak in [True, False]:
                rows = [r for r in allrows if r["weak"] == weak]
                assert len(rows) == 4
                for r in rows:
                    assert len(r["trial_coherences"]) == 25
                    assert r["selected_train_coherence"] == max(r["trial_coherences"])
                groups["weak" if weak else "strong"] = dict(
                    count=4,
                    original_nmse=float(np.median([r["original"]["nmse"] for r in rows])),
                    selected_nmse=float(np.median([r["selected"]["nmse"] for r in rows])),
                    selected_held_coherence=float(
                        np.median([r["selected"]["held_coherence"] for r in rows])
                    ),
                    wrong_held_coherence=float(
                        np.median([r["wrong"]["held_coherence"] for r in rows])
                    ),
                    raw_power=float(np.median([r["raw_mean_power"] for r in rows])),
                )
            ratio = groups["weak"]["raw_power"] / groups["strong"]["raw_power"]
            summary.append(
                dict(
                    signal=signal,
                    receiver=rx,
                    groups=groups,
                    weak_strong_power_ratio=ratio,
                    weak_strong_power_db=float(10 * np.log10(ratio)),
                )
            )
    (BASE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("Verified 32 frames, 800 timing trials and source bindings.")
    for r in summary:
        print(r["signal"], r["receiver"], round(r["weak_strong_power_db"], 3))


if __name__ == "__main__":
    main()
