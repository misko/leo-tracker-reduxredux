"""Post-hoc mechanism diagnostic; no selection, tuning, or new extraction."""

import hashlib
import json

import numpy as np
from study import HERE, ROOT, errors, frames_for


def main():
    results = json.loads((HERE / "results.json").read_text())
    inventory = json.loads((HERE / "inventory.json").read_text())
    for doc in (results, inventory):
        for path, digest in doc["hashes"].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    held = {(r["panel_id"], r["receiver_id"]): r for r in inventory["rows"] if r["role"] == "H"}
    rows = []
    for r in results["rows"]:
        if r["status"] != "ok":
            rows.append(r)
            continue
        a, b, h = r["times_s"]
        ca, cb = r["residual_corrections_hz"][:2]
        constant = (ca + cb) / 2
        baseline = r["arms"]["cached_trajectory"]["residual_frequency_hz"]
        full = r["arms"]["long_trajectory"]["residual_frequency_hz"]
        slope_part = (cb - ca) * (h - (a + b) / 2) / (b - a)
        assert abs(full - (baseline + constant + slope_part)) < 1e-6
        y = frames_for(held[r["panel_id"], r["receiver_id"]])
        nmse = errors(y, baseline + constant)
        full_nmse = np.mean(r["arms"]["long_trajectory"]["frame_nmse"])
        rows.append(
            dict(
                panel_id=r["panel_id"],
                receiver_id=r["receiver_id"],
                status="ok",
                constant_correction_hz=constant,
                slope_contribution_at_held_hz=slope_part,
                constant_only_frame_nmse=nmse.tolist(),
                full_vs_constant_gain=float(np.mean(nmse) - full_nmse),
            )
        )
    summary = {}
    for ds in ("DS7", "DS8", "DS9", "all"):
        valid = [
            r for r in rows if r["status"] == "ok" and (ds == "all" or r["panel_id"].startswith(ds))
        ]
        gains = np.array([r["full_vs_constant_gain"] for r in valid])
        summary[ds] = dict(
            count=len(valid),
            improved=int((gains > 0).sum()),
            mean_gain=float(np.mean(gains)),
            median_gain=float(np.median(gains)),
        )
    paths = [HERE / n for n in ("results.json", "inventory.json", "offset_ablation.py")]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (HERE / "offset_ablation.json").write_text(
        json.dumps(
            dict(
                interpretation="Post-hoc descriptive mechanism check; not a preregistered endpoint",
                hashes=hashes,
                rows=rows,
                summary=summary,
            ),
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
