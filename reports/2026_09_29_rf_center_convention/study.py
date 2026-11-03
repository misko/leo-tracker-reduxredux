"""Matched conditional residual sensitivity to the RF normalization denominator."""

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def correction(y, actual, nominal):
    return np.asarray(y) * (actual / nominal - 1)


def error(e, mask):
    return float(np.median(abs(e[~mask] - e[mask].mean())))


def main():
    plan_path = HERE.parent / "2026_09_29_donor_residual_transfer/plan.json"
    plan = json.loads(plan_path.read_text())
    centers_path = HERE / "centers.json"
    centers = json.loads(centers_path.read_text())["centers"]
    rows, paths = [], [plan_path, centers_path, HERE / "study.py", HERE / "PROTOCOL.md"]
    for u in plan["units"]:
        if u["role"] != "target":
            continue
        p = HERE.parent / "2026_09_29_donor_residual_transfer/runs" / u["unit_id"] / "result.json"
        paths.append(p)
        cases = json.loads(p.read_text())["cases"]
        obs = {}
        for entry in u["group"]["inputs"]:
            a = next(a for a in entry["artifacts"] if a["kind"] == "observations")
            path = Path(a["path"])
            paths.append(path)
            assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == a["sha256"]
            doc = json.loads(path.read_text())
            for t in doc["tracks"]:
                obs[doc["session_id"], t["track_id"]] = t
        for c in cases:
            t = obs[c["session_id"], c["track_id"]]
            options = sorted(
                [v for v in centers if v["channel"] == t["channel"]],
                key=lambda v: abs(v["rf_hz"] - c["rf_hz"]),
            )
            assert len(options) == 2 and abs(options[0]["rf_hz"] - c["rf_hz"]) <= 1e6
            assert abs(options[0]["rf_hz"] - c["rf_hz"]) < abs(options[1]["rf_hz"] - c["rf_hz"])
            nominal = options[0]["rf_hz"]
            actual = c["rf_hz"]
            m = np.asarray(c["mask"], bool)
            np.testing.assert_array_equal(m, t["training_mask"])
            e = np.asarray(c["residual"])
            d = correction(t["measured_hz"], actual, nominal)
            centered = d - d[m].mean()
            rows.append(
                dict(
                    unit_id=c["unit_id"],
                    session_id=c["session_id"],
                    track_id=c["track_id"],
                    number=c["number"],
                    actual_rf_hz=actual,
                    nominal_rf_hz=nominal,
                    edge=options[0]["edge"],
                    factor_ppm=(actual / nominal - 1) * 1e6,
                    old_error_hz=error(e, m),
                    new_error_hz=error(e + d, m),
                    training_change_rms_hz=float(np.sqrt(np.mean(centered[m] ** 2))),
                    maximum_centered_change_hz=float(np.max(abs(centered))),
                )
            )
    assert len(rows) == 3983
    summary = {}
    for ds in ("all", "DS7", "DS8", "DS9"):
        selected = [r for r in rows if ds == "all" or r["unit_id"].startswith(ds)]
        gains = np.array([r["old_error_hz"] - r["new_error_hz"] for r in selected])
        summary[ds] = dict(
            cases=len(selected),
            changed_rf=sum(r["actual_rf_hz"] != r["nominal_rf_hz"] for r in selected),
            wins=int((gains > 1e-6).sum()),
            losses=int((gains < -1e-6).sum()),
            median_gain_hz=float(np.median(gains)),
            mean_gain_hz=float(np.mean(gains)),
            median_training_change_rms_hz=float(
                np.median([r["training_change_rms_hz"] for r in selected])
            ),
            max_centered_change_hz=max(r["maximum_centered_change_hz"] for r in selected),
            max_absolute_factor_ppm=max(abs(r["factor_ppm"]) for r in selected),
        )
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for ds, values in summary.items():
        changed = [
            r
            for r in rows
            if (ds == "all" or r["unit_id"].startswith(ds))
            and r["actual_rf_hz"] != r["nominal_rf_hz"]
        ]
        gains = np.array([r["old_error_hz"] - r["new_error_hz"] for r in changed])
        values["changed_subset_median_gain_hz"] = float(np.median(gains))
        values["changed_subset_mean_gain_hz"] = float(np.mean(gains))
    (HERE / "results.json").write_text(
        json.dumps(dict(hashes=hashes, rows=rows, summary=summary), indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
