"""Plot every model/scale/start on identical second-TRAIN duration views."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import run as runner


def main():
    path = runner.HERE / "results/results.json"
    assert runner.digest(path).split(":")[1] == path.with_suffix(".sha256").read_text().strip()
    result = json.loads(path.read_text())
    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for col, prior in enumerate(("sacramento", "reno")):
        for model, style in [("global", "-"), ("scan", "--")]:
            for scale, color in [(0.2, "C0"), (1.0, "C1"), (5.0, "C2")]:
                arms = sorted(
                    [
                        a
                        for a in result["arms"]
                        if (a["prior"], a["model"], a["scale_s"]) == (prior, model, scale)
                    ],
                    key=lambda a: a["view_scan_count"],
                )
                for row, key in enumerate(("reference_error_km", "held_capped_rms_hz")):
                    axes[row, col].plot(
                        range(4),
                        [a.get(key, float("nan")) for a in arms],
                        style,
                        color=color,
                        marker="o",
                        label=f"{model}, {scale:g} s",
                    )
        axes[0, col].set_title(prior.title())
        axes[0, col].axhline(0.3, color="gray", linestyle=":", label="300 m target")
        for row in range(2):
            axes[row, col].set_xticks(range(4), ["1", "6", "16", "79"])
            axes[row, col].set_xlabel("Nested scan count")
            axes[row, col].grid(alpha=0.2)
    axes[0, 0].set_ylabel("Position error (km)")
    axes[1, 0].set_ylabel("Held capped RMS (Hz)")
    axes[0, 1].legend(fontsize=8)
    figure.suptitle("Second TRAIN group · fixed-identity timing-model replication")
    figure.savefig(runner.HERE / "replication.png", dpi=160)
    keys = [
        "model",
        "prior",
        "scale_s",
        "view_scan_count",
        "reference_error_km",
        "held_capped_rms_hz",
        "held_uncapped_rms_hz",
        "stopping_rule_satisfied",
        "tau_boundary_count",
        "visibility_failure_count",
        "failure",
    ]
    summary = [{key: a[key] for key in keys if key in a} for a in result["arms"]]
    (runner.HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
