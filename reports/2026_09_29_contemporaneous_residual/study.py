"""Other-candidate same-recording slope transfer, with held samples isolated."""

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def training(case):
    mask = np.asarray(case["mask"], bool)
    return np.asarray(case["times"])[mask], np.asarray(case["residual"])[mask]


def slope(t, e):
    z = t - t.mean()
    return float(z @ (e - e.mean()) / (z @ z))


def predictor(target, cases, same_rx):
    t, _ = training(target)
    lo, hi = t.min(), t.max()
    grouped = {}
    for donor in cases:
        if (
            donor["session_id"] != target["session_id"]
            or donor["rf_hz"] != target["rf_hz"]
            or donor["track_id"] == target["track_id"]
            or donor["number"] == target["number"]
            or (donor["receiver_id"] == target["receiver_id"]) != same_rx
        ):
            continue
        dt, de = training(donor)
        overlap = min(hi, dt.max()) - max(lo, dt.min())
        if overlap < 0.5 * (hi - lo):
            continue
        keep = (dt >= lo) & (dt <= hi)
        if keep.sum() < 5 or np.ptp(dt[keep]) < 5:
            continue
        grouped.setdefault(donor["number"], []).append(slope(dt[keep], de[keep]))
    if len(grouped) < 3:
        return None
    return dict(
        slope=float(np.median([np.median(v) for v in grouped.values()])),
        numbers=sorted(grouped),
    )


def error(target, value):
    t, e = training(target)
    held = ~np.asarray(target["mask"], bool)
    ht = np.asarray(target["times"])[held]
    he = np.asarray(target["residual"])[held]
    return float(np.median(abs(he - e.mean() - value * (ht - t.mean()))))


def aggregate(rows):
    result = {"cases": len(rows), "scans": len({r["session_id"] for r in rows})}
    for arm in ("same", "opposite", "own"):
        gains = np.array([r["zero_error"] - r[f"{arm}_error"] for r in rows])
        result[arm] = dict(
            supported=sum(r[arm] is not None for r in rows),
            wins=int((gains > 1e-9).sum()),
            losses=int((gains < -1e-9).sum()),
            median_gain_hz=float(np.median(gains)) if len(gains) else None,
            mean_gain_hz=float(np.mean(gains)) if len(gains) else None,
        )
    return result


def main():
    rows, hashes, sources = [], {}, []
    source = HERE.parent / "2026_09_29_donor_residual_transfer" / "runs"
    for path in sorted(source.glob("DS*_*_8/result.json")):
        payload = json.loads(path.read_text())
        assert payload["role"] == "target"
        sources.append(path)
        cases = payload["cases"]
        for c in cases:
            t, e = training(c)
            same = predictor(c, cases, True)
            opposite = predictor(c, cases, False)
            own = dict(slope=slope(t, e))
            row = {k: c[k] for k in ("unit_id", "session_id", "track_id", "number")}
            row["zero_error"] = error(c, 0)
            for name, estimate in (("same", same), ("opposite", opposite), ("own", own)):
                row[name] = estimate
                row[f"{name}_error"] = error(c, estimate["slope"] if estimate else 0)
            rows.append(row)
    assert len(sources) == 9 and len(rows) == 3983
    for path in sources + [HERE / "study.py", HERE / "PROTOCOL.md"]:
        hashes[str(path.relative_to(HERE.parent.parent))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    matched = [r for r in rows if r["same"] and r["opposite"]]
    summary = {"all": aggregate(rows), "matched": aggregate(matched)}
    for unit in sorted({r["unit_id"] for r in rows}):
        selected = [r for r in rows if r["unit_id"] == unit]
        summary[unit] = {
            "all": aggregate(selected),
            "same_supported": aggregate([r for r in selected if r["same"]]),
            "matched": aggregate([r for r in selected if r["same"] and r["opposite"]]),
        }
    (HERE / "results.json").write_text(json.dumps(dict(hashes=hashes, rows=rows), indent=2) + "\n")
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in ("all", "matched")}, indent=2))


if __name__ == "__main__":
    main()
