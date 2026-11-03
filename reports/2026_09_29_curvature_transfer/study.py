import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def training(case):
    mask = np.asarray(case["mask"], bool)
    return np.asarray(case["times"])[mask], np.asarray(case["residual"])[mask]


def fit_curve(t, y, center, scale):
    x = (np.asarray(t) - center) / scale
    design = np.column_stack([np.ones(len(x)), x, x * x])
    beta, _, rank, _ = np.linalg.lstsq(design, np.asarray(y), rcond=None)
    return float(beta[2]) if rank == 3 else None


def predictor(target, cases, same):
    t, _ = training(target)
    lo, hi = t.min(), t.max()
    center = t.mean()
    scale = np.ptp(t)
    grouped = {}
    donors = []
    for donor in cases:
        if (
            donor["session_id"] != target["session_id"]
            or donor["rf_hz"] != target["rf_hz"]
            or donor["receiver_id"] == target["receiver_id"]
            or donor["track_id"] == target["track_id"]
            or (donor["number"] == target["number"]) != same
        ):
            continue
        dt, de = training(donor)
        if min(hi, dt.max()) - max(lo, dt.min()) < 0.5 * (hi - lo):
            continue
        keep = (dt >= lo) & (dt <= hi)
        if keep.sum() < 8 or np.ptp(dt[keep]) < 10:
            continue
        value = fit_curve(dt[keep], de[keep], center, scale)
        if value is None:
            continue
        grouped.setdefault(donor["number"], []).append(value)
        donors.append(dict(track_id=donor["track_id"], number=donor["number"], coefficient=value))
    if not grouped:
        return None
    return dict(
        coefficient=float(np.median([np.median(v) for v in grouped.values()])), donors=donors
    )


def prediction(target, coefficient):
    t, y = training(target)
    x = (np.asarray(target["times"]) - t.mean()) / np.ptp(t)
    design = np.column_stack([np.ones(len(x)), x])
    mask = np.asarray(target["mask"], bool)
    line = np.linalg.lstsq(design[mask], y, rcond=None)[0]
    projection = np.linalg.lstsq(design[mask], x[mask] ** 2, rcond=None)[0]
    return design @ line + coefficient * (x * x - design @ projection)


def error(target, coefficient):
    held = ~np.asarray(target["mask"], bool)
    return float(
        np.median(abs(np.asarray(target["residual"])[held] - prediction(target, coefficient)[held]))
    )


def save(name, data):
    with (HERE / name).open("x") as f:
        json.dump(data, f, indent=2, allow_nan=False)


def prepare():
    previous = json.loads(
        (HERE.parent / "2026_09_29_candidate_rx_transfer/results.json").read_text()
    )
    for name, h in previous["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h, name
    paths = sorted(
        (HERE.parent / "2026_09_29_donor_residual_transfer/runs").glob("DS*_*_8/result.json")
    )
    assert len(paths) == 9
    save(
        "manifest.json",
        dict(
            inputs=[str(p.relative_to(ROOT)) for p in paths],
            hashes={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in paths + [HERE / "study.py", HERE / "PROTOCOL.md"]
            },
        ),
    )


def summarize(rows):
    out = dict(cases=len(rows))
    for arm in ("same", "other", "own"):
        gains = np.array([r["linear_error"] - r[arm + "_error"] for r in rows])
        out[arm] = dict(
            wins=int((gains > 1e-9).sum()),
            median_gain_hz=float(np.median(gains)) if len(gains) else None,
            mean_gain_hz=float(gains.mean()) if len(gains) else None,
        )
    return out


def run():
    import time

    started = time.monotonic()
    manifest = json.loads((HERE / "manifest.json").read_text())
    for name, h in manifest["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h, name
    rows = []
    excluded = []
    count = 0
    for name in manifest["inputs"]:
        cases = json.loads((ROOT / name).read_text())["cases"]
        count += len(cases)
        for case in cases:
            t, y = training(case)
            if len(t) < 8 or np.ptp(t) < 10 or all(case["mask"]):
                excluded.append(
                    dict(
                        unit=case["unit_id"],
                        track_id=case["track_id"],
                        reason="training/held support",
                    )
                )
                continue
            own = fit_curve(t, y, t.mean(), np.ptp(t))
            if own is None:
                excluded.append(
                    dict(unit=case["unit_id"], track_id=case["track_id"], reason="quadratic rank")
                )
                continue
            same, other = predictor(case, cases, True), predictor(case, cases, False)
            row = {
                k: case[k]
                for k in ("unit_id", "session_id", "track_id", "number", "receiver_id", "rf_hz")
            }
            row.update(
                same=same,
                other=other,
                own=own,
                linear_error=error(case, 0),
                own_error=error(case, own),
                same_error=error(case, same["coefficient"] if same else 0),
                other_error=error(case, other["coefficient"] if other else 0),
            )
            rows.append(row)
    assert count == 3983
    summary = {}
    for ds in ["all", "DS7", "DS8", "DS9"] + sorted({r["unit_id"] for r in rows}):
        subset = [r for r in rows if ds == "all" or r["unit_id"].startswith(ds)]
        summary[ds] = dict(
            all=summarize(subset),
            supported=summarize([r for r in subset if r["same"]]),
            matched=summarize([r for r in subset if r["same"] and r["other"]]),
        )
    save(
        "results.json",
        dict(
            rows=rows,
            excluded=excluded,
            input_tracks=count,
            elapsed_seconds=time.monotonic() - started,
            manifest_sha256=hashlib.sha256((HERE / "manifest.json").read_bytes()).hexdigest(),
        ),
    )
    save("summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("all", "DS7", "DS8", "DS9")}, indent=2))


if __name__ == "__main__":
    import sys

    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "run":
        run()
    else:
        raise ValueError("Unknown command")
