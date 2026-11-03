"""Post-result coverage audit; does not relax the frozen predictor."""

import hashlib
import json
from collections import Counter

import numpy as np
from study import HERE, training


def main():
    result = json.loads((HERE / "results.json").read_text())
    root = HERE.parent.parent
    for path, digest in result["hashes"].items():
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest
    summaries = {}
    for ds in ("DS7", "DS8", "DS9"):
        counts = {
            rx: {stage: Counter() for stage in ("lane", "overlap", "usable")}
            for rx in ("same", "opposite")
        }
        for path in sorted(
            (HERE.parent / "2026_09_29_donor_residual_transfer/runs").glob(f"{ds}_*_8/result.json")
        ):
            cases = json.loads(path.read_text())["cases"]
            for target in cases:
                t, _ = training(target)
                lo, hi = t.min(), t.max()
                for rx in counts:
                    sets = {stage: set() for stage in counts[rx]}
                    for d in cases:
                        if (
                            d["session_id"] != target["session_id"]
                            or d["rf_hz"] != target["rf_hz"]
                            or d["number"] == target["number"]
                            or d["track_id"] == target["track_id"]
                            or (d["receiver_id"] == target["receiver_id"]) != (rx == "same")
                        ):
                            continue
                        sets["lane"].add(d["number"])
                        dt, _ = training(d)
                        if min(hi, dt.max()) - max(lo, dt.min()) < 0.5 * (hi - lo):
                            continue
                        sets["overlap"].add(d["number"])
                        keep = (dt >= lo) & (dt <= hi)
                        if keep.sum() >= 5 and np.ptp(dt[keep]) >= 5:
                            sets["usable"].add(d["number"])
                    for stage, values in sets.items():
                        counts[rx][stage][len(values)] += 1
        summaries[ds] = counts
    rows = result["rows"]
    assert sum(
        sum(v for k, v in summaries[ds]["same"]["usable"].items() if k >= 3) for ds in summaries
    ) == sum(r["same"] is not None for r in rows)
    assert sum(
        sum(v for k, v in summaries[ds]["opposite"]["usable"].items() if k >= 3) for ds in summaries
    ) == sum(r["opposite"] is not None for r in rows)
    (HERE / "coverage.json").write_text(json.dumps(summaries, indent=2) + "\n")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
