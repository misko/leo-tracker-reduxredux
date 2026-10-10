"""Supplemental archive-fallback sensitivity plot from completed evaluation only."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    path = HERE / "evaluation.json"
    evaluation = json.loads(path.read_text())
    rows = evaluation["members"]
    if len(rows) != 193 or len({r["label"] for r in rows}) != 193:
        raise ValueError("complete193 required")
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    verification = {}
    for index, arm in enumerate(("fitted-c", "zero-c")):
        x, y, fallback, labels = [], [], [], []
        for row in rows:
            values = row["arms"][arm]
            if row["status"] != "complete" or not values["timestamp"]["qualified"]:
                raise ValueError("complete qualified timestamp control required")
            use_archive = not values["phase"]["qualified"]
            candidate = values["archive"] if use_archive else values["phase"]
            if not candidate["qualified"]:
                raise ValueError("qualified sensitivity endpoint unavailable")
            x.append(values["timestamp"]["error_km"])
            y.append(candidate["error_km"])
            fallback.append(use_archive)
            if use_archive:
                labels.append(row["label"])
        x, y, fallback = np.asarray(x), np.asarray(y), np.asarray(fallback)
        if not np.isfinite(x).all() or not np.isfinite(y).all() or min(x.min(), y.min()) <= 0:
            raise ValueError("finite positive errors required for logarithmic axes")
        expected = evaluation["groups"]["full"][arm]["archive_fallback_sensitivity"]
        for name, values in (("timestamp", x), ("phase", y)):
            for field, actual in (
                ("mean_km", values.mean()),
                ("median_km", np.median(values)),
                ("p95_km", np.quantile(values, 0.95)),
                ("worst_km", values.max()),
            ):
                np.testing.assert_allclose(actual, expected[name][field], rtol=0, atol=1e-12)
        if int(fallback.sum()) != expected["phase"]["archive_fallbacks"]:
            raise ValueError("fallback count mismatch")
        cdf, scatter = axes[index]
        for values, label, color in (
            (x, "Timestamp control (193 qualified)", "tab:blue"),
            (y, "Phase + archive fallback (192 qualified + 1 fallback)", "tab:orange"),
        ):
            sorted_values = np.sort(values)
            cdf.step(sorted_values, np.arange(1, 194) / 193, where="post", label=label, color=color)
        for value in y[fallback]:
            cdf.scatter(
                [value],
                [np.count_nonzero(y <= value) / 193],
                marker="X",
                s=90,
                color="red",
                zorder=5,
                label="Archive replacement",
            )
        cdf.set_xscale("log")
        cdf.set_xlabel("Position error (km, logarithmic)")
        cdf.set_ylabel("Cumulative fraction of all 193 members")
        cdf.set_title(arm + ": ARCHIVE-FALLBACK sensitivity CDF")
        cdf.legend(fontsize=8)
        scatter.scatter(x[~fallback], y[~fallback], s=20, alpha=0.65, label="Qualified phase")
        scatter.scatter(
            x[fallback],
            y[fallback],
            color="red",
            marker="X",
            s=90,
            label="Archive replacement",
            zorder=5,
        )
        low, high = min(x.min(), y.min()) * 0.8, max(x.max(), y.max()) * 1.2
        scatter.plot([low, high], [low, high], "--", color="gray", label="Equal error")
        scatter.set_xscale("log")
        scatter.set_yscale("log")
        scatter.set_xlim(low, high)
        scatter.set_ylim(low, high)
        scatter.set_xlabel("Timestamp control error (km, logarithmic)")
        scatter.set_ylabel("Phase + archive fallback error (km, logarithmic)")
        scatter.set_title(arm + ": all 193 paired members; lower is better")
        scatter.legend(fontsize=8)
        for axis in (cdf, scatter):
            axis.grid(alpha=0.2, which="both")
        verification[arm] = dict(
            members=193,
            phase_qualified=int((~fallback).sum()),
            archive_fallbacks=int(fallback.sum()),
            fallback_labels=labels,
            timestamp_mean_km=float(x.mean()),
            sensitivity_mean_km=float(y.mean()),
            timestamp_worst_km=float(x.max()),
            sensitivity_worst_km=float(y.max()),
            metric_check="mean/median/p95/worst agree with evaluation within1e-12",
        )
    fig.suptitle("ARCHIVE-FALLBACK SENSITIVITY — not a fully qualified phase result", fontsize=15)
    output = HERE / "fallback-comparison.png"
    fig.savefig(output, dpi=170)
    plt.close(fig)
    (HERE / "sensitivity-integrity.json").write_text(
        json.dumps(
            dict(
                protocol_sha256=evaluation["protocol_sha256"],
                verification=verification,
                sha256={p.name: digest(p) for p in (path, Path(__file__), output)},
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
