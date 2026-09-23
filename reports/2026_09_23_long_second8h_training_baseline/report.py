"""Verify the saved baseline and plot all eight replication outcomes."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    directory = HERE / "results"
    path = directory / "inference.json"
    assert digest(path).split(":")[1] == path.with_suffix(".sha256").read_text().strip()
    inference = json.loads(path.read_text())
    results = json.loads((directory / "results.json").read_text())
    assert len(inference["arms"]) == len(results["arms"]) == 8
    assert digest(HERE / "search.py") == inference["bindings"]["tool"]
    for key, relative in {
        "single_tool": "reports/2026_09_23_long_training_search/search.py",
        "fast_loader": "reports/2026_09_23_long_training_fast_score/loader.py",
        "manifest": "reports/2026_09_23_long_training_cache_second8h/manifest.json",
    }.items():
        assert digest(ROOT / relative) == inference["bindings"][key]
    assert inference["session_ids"] == results["session_ids"]
    rows = []
    for original, evaluated in zip(inference["arms"], results["arms"], strict=True):
        point = evaluated["search"]["selected"]
        for key, value in original["search"]["selected"].items():
            assert point[key] == value
        rows.append(
            {
                "prior": evaluated["prior"],
                "scans": evaluated["scan_count"],
                "track_count": sum(len(s["tracks"]) for s in point["scans"]),
                "train_rms_hz": point["objective_rmse_hz"],
                "held_rms_hz": point["reserved_capped800_rmse_hz"],
                "error_km": point["reference_error_km"],
            }
        )
    figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for prior in ("sacramento", "reno"):
        selected = [r for r in rows if r["prior"] == prior]
        for axis, key in zip(axes, ("error_km", "held_rms_hz"), strict=True):
            axis.plot(range(4), [r[key] for r in selected], "o-", label=prior.title())
            axis.set_xticks(range(4), ["1", "6", "16", "79"])
            axis.set_xlabel("Nested scan count")
            axis.grid(alpha=0.25)
    axes[0].axhline(0.3, color="gray", linestyle="--", label="300 m target")
    axes[0].set_ylabel("Reference error (km)")
    axes[1].set_ylabel("Held capped RMS (Hz)")
    axes[0].legend()
    axes[1].legend()
    figure.suptitle("Second eight-hour TRAIN group · blind zero-epoch baseline")
    figure.savefig(HERE / "baseline.png", dpi=160)
    (HERE / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    (directory / "results.sha256").write_text(
        digest(directory / "results.json").split(":")[1] + "\n"
    )
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
