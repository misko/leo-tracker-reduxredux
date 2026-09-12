"""Plot every timing comparison as GLRT/PSS rows and the same three radio lanes."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path("/srv/bulk/leo/experiments")
LANES = ("native25", "derived2p5", "recorded2p5")
LABELS = ("25 MS/s native", "2.5 MS/s downsampled", "2.5 MS/s independent capture")
COLORS = ("#157f91", "#c76524", "#7d58a0")


def alternate_residual(t, y):
    """Keep every observation; fit even indices and evaluate odd indices."""
    t, y = np.asarray(t), np.asarray(y)
    train = np.arange(len(t)) % 2 == 0
    origin = np.median(y[train])
    design = np.vander(t - 1.125, 3)
    coef = np.linalg.lstsq(design[train], y[train] - origin, rcond=None)[0]
    residual = y - origin - design @ coef
    return residual, float(np.sqrt(np.mean(residual[~train] ** 2)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output
    if out.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("QNAP is read-only")
    out.mkdir(exist_ok=True)
    v2 = ROOT / "paired-five-pss-bandwidth-20260912-v2-fractional"
    v4 = ROOT / "paired-five-glrt-pss-tle-20260912-v4"
    selected = json.loads((v4 / "selection.json").read_text())["selected"]
    glrt = json.loads((v4 / "fractional-glrt-comparison.json").read_text())
    pss = json.loads((v2 / "summary.json").read_text())
    bias = json.loads((out / "glrt-sample-phase-bias.json").read_text())["records"]
    records = []
    recovery = []
    for c in selected:
        fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
        limits = [0.0, 0.0]
        for row, source in enumerate((glrt, pss)):
            for col, lane in enumerate(LANES):
                r = next(
                    d for d in source if d["capture_id"] == c["capture_id"] and d["lane"] == lane
                )
                start = c["recorded_start_s" if col == 2 else "native_start_s"]
                t = np.asarray(r["time_s"]) - (start if row else 0)
                y = np.asarray(r["phase_s"]) * 1e9 if row else np.asarray(r["value"])
                residual, rms = alternate_residual(t, y)
                expected = r["heldout_rms_ns"] if row else r["diagnostics"]["alternate_rms"]
                if not np.isclose(rms, expected, atol=0.001):
                    raise ValueError("plot disagrees with frozen comparison RMS")
                record = dict(
                    capture_id=c["capture_id"],
                    lane=lane,
                    method="PSS" if row else "GLRT",
                    count=len(t),
                    alternate_rms_ns=rms,
                    time_s=t.tolist(),
                    residual_ns=residual.tolist(),
                )
                records.append(record)
                ax = axes[row, col]
                ax.scatter(t, residual, s=5 if row else 10, alpha=0.55, color=COLORS[col])
                ax.axhline(0, color="#444444", linewidth=0.6)
                ax.set_title(
                    f"{LABELS[col]}\n{'PSS' if row else 'GLRT'} · alternate-frame RMS {rms:.1f} ns"
                )
                ax.set_xlabel("Seconds into selected interval")
                ax.set_ylabel("Timing measurement − quadratic prediction (ns)")
                ax.grid(alpha=0.2)
                limits[row] = max(limits[row], float(np.max(abs(residual))))
                if row:
                    ax.text(
                        0.02,
                        0.97,
                        f"Strong peaks: {r['strong_fraction']:.0%}; all {len(t)} shown",
                        transform=ax.transAxes,
                        va="top",
                        fontsize=8,
                        bbox=dict(facecolor="white", alpha=0.85, edgecolor="none"),
                    )
                else:
                    ax.text(
                        0.02,
                        0.97,
                        f"Fractional results: {r['complete_count']}/{r['window_count']}",
                        transform=ax.transAxes,
                        va="top",
                        fontsize=8,
                        bbox=dict(facecolor="white", alpha=0.85, edgecolor="none"),
                    )
        for row in range(2):
            limit = max(80 if row == 0 else 2300, limits[row] * 1.13)
            for ax in axes[row]:
                ax.set_ylim(-limit, limit)
                ax.set_xlim(0, 2.25)
        fig.suptitle(
            f"Current fractional timing · dwell {c['capture_id'][-6:]}\n"
            "GLRT above, PSS below; same vertical scale within each row, "
            "different scales between rows\n"
            "Quadratic fitted on alternating measurements; "
            "all available measurements retained; no outlier correction",
            fontsize=12,
        )
        fig.savefig(out / f"timing-residuals-{c['capture_id'][-6:]}.png", dpi=150)
        plt.close(fig)
        raw = json.loads((out / "recovery" / (c["capture_id"] + ".json")).read_text())["records"]
        rejected = [r for r in raw if r["original_status"] == "rejected"]
        supported = [r for r in rejected if r["interior"] and r["cfo_interior"]]
        controls = [r for r in raw if r["original_status"] == "accepted"]

        def rms_of(rows, key):
            return float(np.sqrt(np.mean([r[key] ** 2 for r in rows])))

        recovery.append(
            dict(
                capture_id=c["capture_id"],
                rejected_count=len(rejected),
                supported_count=len(supported),
                unsupported_count=len(rejected) - len(supported),
                supported_original_rms_ns=rms_of(supported, "original_innovation_ns"),
                supported_joint_rms_ns=rms_of(supported, "joint_innovation_ns"),
                all_rejected_joint_rms_ns=rms_of(rejected, "joint_innovation_ns"),
                controls_count=len(controls),
                controls_original_rms_ns=rms_of(controls, "original_innovation_ns"),
                controls_joint_rms_ns=rms_of(controls, "joint_innovation_ns"),
                rejected_median_power_ratio=float(
                    np.median([r["joint_power"] / r["original_power"] for r in rejected])
                ),
            )
        )

    fig, axes = plt.subplots(2, 3, figsize=(15, 8.5), constrained_layout=True)
    x = np.arange(5)
    for col, lane in enumerate(LANES):
        ax = axes[0, col]
        rows = [
            next(r for r in bias if r["capture_id"] == c["capture_id"] and r["lane"] == lane)
            for c in selected
        ]
        ax.bar(
            x - 0.17,
            [r["late_baseline_rms_ns"] for r in rows],
            width=0.32,
            color="#999999",
            label="Quadratic only",
        )
        ax.bar(
            x + 0.17,
            [r["late_periodic_model_rms_ns"] for r in rows],
            width=0.32,
            color=COLORS[col],
            label="+ sample-phase bias model",
        )
        ax.set_title(f"{LABELS[col]}\nGLRT: fit first 60%, evaluate last 40%")
        ax.set_ylabel("Late timing prediction residual RMS (ns)")
        ax.set_ylim(0, 65)
        ax.legend(fontsize=8)
        ax = axes[1, col]
        if col == 0:
            ax.bar(
                x - 0.17,
                [r["supported_original_rms_ns"] for r in recovery],
                width=0.32,
                color="#999999",
                label="Original rejected measurements",
            )
            ax.bar(
                x + 0.17,
                [r["supported_joint_rms_ns"] for r in recovery],
                width=0.32,
                color=COLORS[col],
                label="Local timing + CFO re-search",
            )
            ax.set_yscale("log")
            ax.set_ylim(1, 5000)
            ax.set_ylabel("RMS against frozen prior (ns; log scale)")
            ax.set_title(
                "PSS: raw-IQ recovery on the SAME supported rejects\n"
                "624/671 supported; 47 boundary cases unresolved"
            )
            ax.legend(fontsize=7, loc="upper right")
            for i, r in enumerate(recovery):
                ax.text(
                    i,
                    1200,
                    f"{r['supported_count']}/{r['rejected_count']}",
                    ha="center",
                    fontsize=8,
                )
        else:
            rows = [
                next(r for r in pss if r["capture_id"] == c["capture_id"] and r["lane"] == lane)
                for c in selected
            ]
            ax.bar(x, [r["heldout_rms_ns"] for r in rows], color=COLORS[col], width=0.6)
            ax.set_title(
                "PSS: current fractional timing, all peaks\n"
                "Local timing/CFO recovery NOT YET evaluated"
            )
            ax.set_ylabel("Alternate-frame timing residual RMS (ns)")
            ax.set_ylim(0, 1250)
        for row in range(2):
            axes[row, col].set_xticks(x, [c["capture_id"][-6:] for c in selected], rotation=25)
            axes[row, col].set_xlabel("Dwell ID suffix")
            axes[row, col].grid(axis="y", alpha=0.2)
            axes[row, col].set_axisbelow(True)
    fig.suptitle(
        "Current correction status · both estimators and all three capture lanes\n"
        "Panels explicitly use different validation protocols; "
        "compare before/after only within a panel\n"
        "Offline diagnostics: lower residuals do not establish "
        "absolute timing/Doppler accuracy or a deployed lock",
        fontsize=12,
    )
    fig.savefig(out / "timing-current-status.png", dpi=150)
    plt.close(fig)
    (out / "timing-current-status.json").write_text(
        json.dumps(
            dict(
                residual_protocol="Alternating measurements fit an ordinary quadratic; "
                "all peaks retained. Matches frozen RMS.",
                residual_records=records,
                recovery=recovery,
            ),
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
