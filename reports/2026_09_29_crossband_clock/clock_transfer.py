"""Bounded cross-band residual prediction with explicit RF scaling."""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "2026_09_29_contemporaneous_residual"
sys.path.insert(0, str(PARENT))
from study import error, slope, training  # noqa: E402


def predict(target, cases, same_rx=True):
    t, _ = training(target)
    lo, hi = t.min(), t.max()
    stages = {k: set() for k in ("other_rf", "overlap", "usable")}
    values, bands = {}, set()
    for d in cases:
        if (
            d["session_id"] != target["session_id"]
            or d["rf_hz"] == target["rf_hz"]
            or d["number"] == target["number"]
            or d["track_id"] == target["track_id"]
            or (d["receiver_id"] == target["receiver_id"]) != same_rx
        ):
            continue
        stages["other_rf"].add(d["number"])
        dt, de = training(d)
        if min(hi, dt.max()) - max(lo, dt.min()) < 0.5 * (hi - lo):
            continue
        stages["overlap"].add(d["number"])
        keep = (dt >= lo) & (dt <= hi)
        if keep.sum() < 5 or np.ptp(dt[keep]) < 5:
            continue
        stages["usable"].add(d["number"])
        bands.add(d["rf_hz"])
        s = slope(dt[keep], de[keep])
        values.setdefault(d["number"], []).append([s, s * d["rf_hz"] / target["rf_hz"]])
    counts = {k: len(v) for k, v in stages.items()}
    if len(values) < 3:
        return None, counts
    estimates = np.median([np.median(v, axis=0) for v in values.values()], axis=0)
    return dict(
        fractional=float(estimates[0]),
        additive=float(estimates[1]),
        numbers=sorted(values),
        rf_hz=sorted(bands),
    ), counts


def summarize(rows):
    result = dict(cases=len(rows), scans=len({r["session_id"] for r in rows}))
    for arm in ("fractional", "additive", "opposite"):
        g = np.asarray([r["zero"] - r[arm] for r in rows])
        result[arm] = dict(
            wins=int((g > 1e-9).sum()),
            losses=int((g < -1e-9).sum()),
            median_gain_hz=float(np.median(g)) if len(g) else None,
            mean_gain_hz=float(np.mean(g)) if len(g) else None,
        )
    return result


def main():
    rows, coverage, hashes = [], {}, {}
    prior = json.loads((PARENT / "results.json").read_text())
    root = HERE.parent.parent
    for name, digest in prior["hashes"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
    paths = sorted(
        (HERE.parent / "2026_09_29_donor_residual_transfer/runs").glob("DS*_*_8/result.json")
    )
    assert len(paths) == 9
    for path in paths:
        cases = json.loads(path.read_text())["cases"]
        unit = path.parent.name
        counts = {
            rx: {stage: Counter() for stage in ("other_rf", "overlap", "usable")}
            for rx in ("same", "opposite")
        }
        for c in cases:
            same, sc = predict(c, cases)
            opposite, oc = predict(c, cases, False)
            for rx, count in (("same", sc), ("opposite", oc)):
                for stage, n in count.items():
                    counts[rx][stage][n] += 1
            row = {k: c[k] for k in ("unit_id", "session_id", "track_id", "number")}
            row.update(same=same, peer=opposite, zero=error(c, 0))
            for arm in ("fractional", "additive"):
                row[arm] = error(c, same[arm] if same else 0)
            row["opposite"] = error(c, opposite["fractional"] if opposite else 0)
            rows.append(row)
        coverage[unit] = counts
    assert len(rows) == 3983
    for path in paths + [HERE / "clock_transfer.py", HERE / "PROTOCOL.md", PARENT / "study.py"]:
        hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = {}
    for key in ("all", "DS7", "DS8", "DS9"):
        selected = [r for r in rows if key == "all" or r["unit_id"].startswith(key)]
        summary[key] = dict(
            all=summarize(selected),
            supported=summarize([r for r in selected if r["same"]]),
            matched=summarize([r for r in selected if r["same"] and r["peer"]]),
        )
    for name, value in (
        ("results", dict(hashes=hashes, rows=rows)),
        ("summary", summary),
        ("coverage", coverage),
    ):
        (HERE / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
