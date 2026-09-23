"""Plot every pooled conditional result against separate-group fits."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import run as runner


def main():
    path = runner.HERE / "results/results.json"
    assert runner.digest(path).split(":")[1] == path.with_suffix(".sha256").read_text().strip()
    result = json.loads(path.read_text())
    figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for prior, style in [("sacramento", "o-"), ("reno", "x--")]:
        arms = [a for a in result["arms"] if a["prior"] == prior]
        for axis, key in zip(axes, ["reference_error_km", "held_capped_rms_hz"], strict=True):
            axis.plot(range(3), [a[key] for a in arms], style, label=prior.title())
            axis.set_xticks(range(3), ["0.2", "1", "5"])
            axis.set_xlabel("Regularization scale (s)")
            axis.grid(alpha=0.2)
    axes[0].axhline(0.3, color="gray", linestyle=":", label="300 m target")
    axes[0].set_ylabel("Position error (km)")
    axes[1].set_ylabel("Held capped RMS (Hz)")
    axes[0].legend()
    axes[1].legend()
    figure.suptitle("Pooled 151 TRAIN scans · one position, per-scan epoch corrections")
    figure.savefig(runner.HERE / "pooled.png", dpi=160)
    keys = [
        "prior",
        "scale_s",
        "reference_error_km",
        "held_capped_rms_hz",
        "stopping_rule_satisfied",
        "tau_boundary_count",
        "visibility_failure_count",
        "track_count",
    ]
    (runner.HERE / "summary.json").write_text(
        json.dumps([{k: a[k] for k in keys} for a in result["arms"]], indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
