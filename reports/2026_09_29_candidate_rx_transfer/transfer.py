"""Candidate-conditioned residual transfer across receivers."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "2026_09_29_contemporaneous_residual"
sys.path.insert(0, str(BASE))
from study import error, slope, training  # noqa: E402


def predict(target, cases, same_number=True):
    t, _ = training(target)
    lo, hi = t.min(), t.max()
    values, donors = {}, []
    for d in cases:
        if (
            d["session_id"] != target["session_id"]
            or d["rf_hz"] != target["rf_hz"]
            or d["receiver_id"] == target["receiver_id"]
            or d["track_id"] == target["track_id"]
            or (d["number"] == target["number"]) != same_number
        ):
            continue
        dt, de = training(d)
        if min(hi, dt.max()) - max(lo, dt.min()) < 0.5 * (hi - lo):
            continue
        keep = (dt >= lo) & (dt <= hi)
        if keep.sum() < 5 or np.ptp(dt[keep]) < 5:
            continue
        values.setdefault(d["number"], []).append(slope(dt[keep], de[keep]))
        donors.append(dict(track_id=d["track_id"], number=d["number"]))
    if not values:
        return None
    return dict(slope=float(np.median([np.median(v) for v in values.values()])), donors=donors)


def summarize(rows):
    out = dict(cases=len(rows), scans=len({r["session_id"] for r in rows}))
    for arm in ("candidate", "other", "own"):
        gains = np.asarray([r["zero"] - r[arm] for r in rows])
        out[arm] = dict(
            wins=int((gains > 1e-9).sum()),
            losses=int((gains < -1e-9).sum()),
            median_gain_hz=float(np.median(gains)) if len(gains) else None,
            mean_gain_hz=float(np.mean(gains)) if len(gains) else None,
        )
    gains = np.asarray([r["other"] - r["candidate"] for r in rows])
    out["candidate_vs_other"] = dict(
        wins=int((gains > 1e-9).sum()),
        median_gain_hz=float(np.median(gains)) if len(gains) else None,
    )
    return out


def main():
    root = HERE.parent.parent
    prior = json.loads((BASE / "results.json").read_text())
    for path, digest in prior["hashes"].items():
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest
    paths = sorted(
        (HERE.parent / "2026_09_29_donor_residual_transfer/runs").glob("DS*_*_8/result.json")
    )
    rows = []
    for path in paths:
        cases = json.loads(path.read_text())["cases"]
        for c in cases:
            candidate, other = predict(c, cases), predict(c, cases, False)
            t, e = training(c)
            row = {k: c[k] for k in ("unit_id", "session_id", "track_id", "number", "receiver_id")}
            row.update(
                candidate_predictor=candidate,
                other_predictor=other,
                zero=error(c, 0),
                own=error(c, slope(t, e)),
            )
            row["candidate"] = error(c, candidate["slope"] if candidate else 0)
            row["other"] = error(c, other["slope"] if other else 0)
            rows.append(row)
    assert len(paths) == 9 and len(rows) == 3983
    summary = {}
    for label in ["all", "DS7", "DS8", "DS9"] + sorted({r["unit_id"] for r in rows}):
        subset = [r for r in rows if label == "all" or r["unit_id"].startswith(label)]
        summary[label] = dict(
            all=summarize(subset),
            supported=summarize([r for r in subset if r["candidate_predictor"]]),
            matched=summarize(
                [r for r in subset if r["candidate_predictor"] and r["other_predictor"]]
            ),
        )
    hashes = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths + [HERE / "transfer.py", HERE / "PROTOCOL.md", BASE / "study.py"]
    }
    (HERE / "results.json").write_text(json.dumps(dict(hashes=hashes, rows=rows), indent=2) + "\n")
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in ("all", "DS7", "DS8", "DS9")}, indent=2))


if __name__ == "__main__":
    main()
