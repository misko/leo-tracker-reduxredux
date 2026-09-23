"""Compare conditional and joint fits on both complete TRAIN groups."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import run as runner


def main():
    paths = {
        "first": runner.ROOT
        / "reports/2026_09_23_long_joint_epoch_association/results/results.json",
        "second": runner.HERE / "results/results.json",
        "conditional": runner.ROOT
        / "reports/2026_09_23_second_train_epoch_replication/results/results.json",
    }
    data = {}
    for key, path in paths.items():
        assert runner.digest(path).split(":")[1] == path.with_suffix(".sha256").read_text().strip()
        data[key] = json.loads(path.read_text())
    figure, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for prior, style in [("sacramento", "o-"), ("reno", "x--")]:
        for key, label, color in [
            ("first", "First TRAIN joint", "C0"),
            ("second", "Second TRAIN joint", "C1"),
            ("conditional", "Second TRAIN conditional", "C2"),
        ]:
            arms = sorted(
                [
                    a
                    for a in data[key]["arms"]
                    if a["prior"] == prior
                    and (
                        key != "conditional"
                        or (a["model"] == "scan" and a["view_scan_count"] == 79)
                    )
                ],
                key=lambda a: a["scale_s"],
            )
            for axis, metric in zip(
                axes, ["reference_error_km", "held_capped_rms_hz"], strict=True
            ):
                values = [a.get(metric, a.get("reserved_capped800_rmse_hz")) for a in arms]
                axis.plot(range(3), values, style, color=color, label=f"{label} · {prior}")
                axis.set_xticks(range(3), ["0.2", "1", "5"])
                axis.set_xlabel("Regularization scale (s)")
                axis.grid(alpha=0.2)
    axes[0].set_ylabel("Position error (km)")
    axes[1].set_ylabel("Held capped RMS (Hz)")
    axes[0].axhline(0.3, color="gray", linestyle=":", label="300 m target")
    axes[1].legend(fontsize=7)
    figure.suptitle("Full eight-hour TRAIN groups · all predefined settings")
    figure.savefig(runner.HERE / "comparison.png", dpi=160)
    keys = [
        "prior",
        "scale_s",
        "reference_error_km",
        "held_capped_rms_hz",
        "held_uncapped_rms_hz",
        "stop_reason",
        "tau_boundary_count",
        "visibility_failure_count",
    ]
    summary = [
        {**{key: a[key] for key in keys}, "cycles": len(a["trace"])} for a in data["second"]["arms"]
    ]
    (runner.HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
