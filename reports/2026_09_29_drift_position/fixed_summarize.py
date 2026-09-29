"""Verify integration receipts and summarize all declared allocations."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(p):
    return json.loads(p.read_text())


def main():
    plan = read(HERE / "fixed-plan.json")
    bindings = {}
    results = []
    distinct = {}
    for unit in plan["units"]:
        folder = HERE / "fixed-runs" / unit["unit_id"]
        assert read(folder / "exit.json")["exit_code"] == 0
        for name, value in read(folder / "seal.json")["sha256"].items():
            assert name not in bindings or bindings[name] == value
            bindings[name] = value
        result = read(folder / "result.json")
        assert result["audit_passed"] and result["x"] == unit["x"]
        arms = result["arms"]
        assert list(arms) == plan["arms"]
        base = arms["none"]
        row = {"unit_id": unit["unit_id"], "arms": {}}
        for arm, outcome in arms.items():
            assert (
                abs(sum(r["held_log_score"] for r in outcome["rows"]) - outcome["held_log_score"])
                < 1e-8
            )
            assert len(outcome["rows"]) == len(outcome["corrections"])
            for old, new, receipt in zip(
                base["rows"], outcome["rows"], outcome["corrections"], strict=True
            ):
                key = (new["session_id"], new["track_id"])
                assert key == (old["session_id"], old["track_id"])
                assert key == (receipt["session_id"], receipt["track_id"])
                if not receipt["corrected"]:
                    assert abs(old["held_log_score"] - new["held_log_score"]) < 1e-8
                    assert abs(old["training_log_score"] - new["training_log_score"]) < 1e-8
                if unit["unit_id"].endswith("_8"):
                    identity = (arm, *key)
                    assert identity not in distinct
                    distinct[identity] = (unit["unit_id"][:3], receipt["corrected"])
            row["arms"][arm] = {
                "held_delta_nats": outcome["held_log_score"] - base["held_log_score"],
                "training_delta_nats": outcome["training_log_score"] - base["training_log_score"],
                "corrected_tracks": sum(r["corrected"] for r in outcome["corrections"]),
                "tracks": len(outcome["rows"]),
            }
        results.append(row)
    for name, value in bindings.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value, name
    coverage, aggregate = {}, {}
    for arm in plan["arms"]:
        coverage[arm] = {}
        for ds in ("DS7", "DS8", "DS9"):
            selected = [
                (key, changed)
                for key, (dataset, changed) in distinct.items()
                if key[0] == arm and dataset == ds
            ]
            coverage[arm][ds] = {
                "tracks": len(selected),
                "corrected_tracks": sum(c for _, c in selected),
                "corrected_scans": len({k[1] for k, c in selected if c}),
            }
        values = [r["arms"][arm]["held_delta_nats"] for r in results]
        aggregate[arm] = {
            "better": sum(v > 1e-8 for v in values),
            "tied": sum(abs(v) <= 1e-8 for v in values),
            "worse": sum(v < -1e-8 for v in values),
            "median_delta_nats": float(np.median(values)),
        }
    summary = dict(audit_passed=True, panels=results, coverage=coverage, aggregate=aggregate)
    with (HERE / "fixed-summary.json").open("x") as f:
        json.dump(summary, f, indent=2, allow_nan=False)
    fig, ax = plt.subplots(figsize=(12, 5), layout="constrained")
    x = np.arange(len(results))
    for j, arm in enumerate(plan["arms"][1:]):
        ax.bar(
            x + (j - 1) * 0.25,
            [r["arms"][arm]["held_delta_nats"] for r in results],
            width=0.25,
            label=arm.replace("_", " "),
        )
    ax.axhline(0, color="black", linewidth=0.7)
    ax.set_xticks(x, [r["unit_id"].replace("_", " ") for r in results], rotation=65, ha="right")
    ax.set_ylabel("Held log-score change (nats)")
    ax.set_title("Differential drift at unchanged locations — all panels, no geographic fit")
    ax.legend()
    for suffix in ("png", "svg"):
        fig.savefig(HERE / ("fixed-comparison." + suffix), dpi=160)
    plt.close(fig)
    print(json.dumps({"coverage": coverage, "aggregate": aggregate}, indent=2))


if __name__ == "__main__":
    main()
