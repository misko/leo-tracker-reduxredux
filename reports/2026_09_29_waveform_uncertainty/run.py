import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from model import jackknife_sigma, line_predict

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PREV = HERE.parent / "2026_09_29_waveform_trajectory"
sys.path.insert(0, str(PREV))
from study import errors, fit, frames_for  # noqa: E402


def main():
    plan = json.loads((HERE / "plan.json").read_text())
    inventory = json.loads((HERE / "inventory.json").read_text())
    for doc in (plan, inventory):
        for path, digest in doc["hashes"].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    expected = {(r["unit_id"], r["receiver_id"]) for r in plan["selections"]}
    assert len(inventory["rows"]) == len(expected)
    assert {(r["unit_id"], r["receiver_id"]) for r in inventory["rows"]} == expected
    groups = {}
    for row in inventory["rows"]:
        groups.setdefault((row["panel_id"], row["receiver_id"]), []).append(row)
    results = []
    for (panel, rx), group in groups.items():
        result = dict(panel_id=panel, receiver_id=rx, status="ok")
        try:
            training = sorted(
                (r for r in group if r["role"].startswith("T")), key=lambda r: r["time_s"]
            )
            held = sorted(
                (r for r in group if r["role"].startswith("H")), key=lambda r: r["time_s"]
            )
            assert len(training) == 4 and 1 <= len(held) <= 2
            assert len({r["edge"] for r in group}) == 1
            anchor = training[0]["actual_rf_hz"]
            observations = []
            for row in training:
                frames = frames_for(row)
                frequency = fit(frames, np.arange(20, 220))
                loo = [fit(np.delete(frames, i, axis=0), np.arange(20, 220)) for i in range(8)]
                observations.append(
                    dict(
                        time_s=row["time_s"],
                        visit=row["visit"],
                        residual_frequency_hz=frequency,
                        jackknife_hz=loo,
                        sigma_hz=jackknife_sigma(loo),
                        boundary=abs(frequency) >= 1499.999,
                        jackknife_boundaries=sum(abs(f) >= 1499.999 for f in loo),
                    )
                )
            times = [r["time_s"] for r in training]
            targets = [r["time_s"] for r in held]
            cached = np.array(
                [
                    r["actual_rf_hz"] - anchor + r["candidate"]["fractional_tracking_cfo_hz"]
                    for r in training
                ]
            )
            corrections = np.array([r["residual_frequency_hz"] for r in observations])
            sigmas = np.array([r["sigma_hz"] for r in observations])
            predictions, slopes = {}, {}
            for name, values, weights in (
                ("cached_ols", cached, None),
                ("refined_ols", cached + corrections, None),
                ("cached_wls", cached, sigmas),
                ("refined_wls", cached + corrections, sigmas),
            ):
                predictions[name], slopes[name] = line_predict(times, values, targets, weights)
            evaluations = []
            for i, row in enumerate(held):
                frames = frames_for(row)
                reference = (
                    row["actual_rf_hz"] - anchor + row["candidate"]["fractional_tracking_cfo_hz"]
                )
                frequencies = {
                    name: float(value[i] - reference) for name, value in predictions.items()
                }
                frequencies["cached_held"] = 0.0
                evaluations.append(
                    dict(
                        visit=row["visit"],
                        time_s=row["time_s"],
                        forecast_s=row["time_s"] - times[-1],
                        arms={
                            name: dict(
                                residual_frequency_hz=f, frame_nmse=errors(frames, f).tolist()
                            )
                            for name, f in frequencies.items()
                        },
                    )
                )
            result.update(training=observations, held=evaluations, slopes_hz_s=slopes)
        except Exception as exc:
            result.update(status="failed", reason=f"{type(exc).__name__}: {exc}")
        results.append(result)
    arms = ("cached_ols", "refined_ols", "cached_wls", "refined_wls", "cached_held")
    comparisons = {
        "refinement_ols": ("cached_ols", "refined_ols"),
        "refinement_wls": ("cached_wls", "refined_wls"),
        "weighting_refined": ("refined_ols", "refined_wls"),
        "combined": ("cached_ols", "refined_wls"),
    }
    summary = {}
    for ds in ("DS7", "DS8", "DS9", "all"):
        selected = [r for r in results if ds == "all" or r["panel_id"].startswith(ds)]
        valid = [r for r in selected if r["status"] == "ok"]
        means = {
            arm: np.array(
                [np.mean([np.mean(h["arms"][arm]["frame_nmse"]) for h in r["held"]]) for r in valid]
            )
            for arm in arms
        }
        summary[ds] = dict(
            planned=len(selected),
            returned=len(valid),
            held_visits=sum(len(r["held"]) for r in valid),
            mean_nmse={arm: float(np.mean(v)) if len(v) else None for arm, v in means.items()},
            comparisons={
                name: dict(
                    improved=int(np.sum(means[a] > means[b])),
                    mean_gain=float(np.mean(means[a] - means[b])) if valid else None,
                    median_gain=float(np.median(means[a] - means[b])) if valid else None,
                )
                for name, (a, b) in comparisons.items()
            },
            boundaries=sum(t["boundary"] for r in valid for t in r["training"]),
            jackknife_boundaries=sum(
                t["jackknife_boundaries"] for r in valid for t in r["training"]
            ),
            floor_visits=sum(t["sigma_hz"] < 25 for r in valid for t in r["training"]),
            median_sigma_hz=float(np.median([t["sigma_hz"] for r in valid for t in r["training"]]))
            if valid
            else None,
        )
    files = [HERE / n for n in ("plan.json", "inventory.json", "PROTOCOL.md", "run.py", "model.py")]
    files += [PREV / "study.py"]
    parent_result = json.loads((PREV / "results.json").read_text())
    # Include numerical helper/reference dependencies, excluding predecessor data.
    files += [
        ROOT / name
        for name in parent_result["hashes"]
        if name.endswith((".py", ".mat")) or name.startswith("tests/fixtures/")
    ]
    files += [ROOT / r["path"] for r in inventory["rows"] if r["status"] == "ok"]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (HERE / "results.json").write_text(
        json.dumps(dict(hashes=hashes, rows=results, summary=summary), indent=2, allow_nan=False)
        + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
