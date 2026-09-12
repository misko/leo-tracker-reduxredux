"""Early-fit/late-evaluation diagnostic of fractional GLRT sample-phase bias."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def fit_bias(t, y, frame, rate):
    train = t < 1.35
    origin = float(np.median(y[train]))
    x = t - 0.675
    design = np.vander(x, 3)
    base = np.linalg.lstsq(design[train], (y - origin)[train], rcond=None)[0]
    prediction = design @ base + origin
    # Frame identity is discrete. Fractional phase uses the early-only smooth
    # prediction, not each evaluated observation's noisy fractional coordinate.
    phase = np.mod(frame * rate / 750 + prediction * rate * 1e-9, 1)
    angle = 2 * np.pi * phase
    periodic = np.array([np.sin(angle), np.cos(angle), np.sin(2 * angle), np.cos(2 * angle)]).T
    augmented = np.column_stack([design, periodic])
    coef = np.linalg.lstsq(augmented[train], (y - origin)[train], rcond=None)[0]
    return dict(
        train=train,
        phase=phase,
        baseline=prediction,
        corrected_prediction=origin + augmented @ coef,
        smooth=origin + design @ coef[:3],
        coefficients=coef,
        origin_ns=origin,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output
    if out.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("QNAP is read-only")
    out.mkdir(exist_ok=True)
    source = Path("/srv/bulk/leo/experiments/paired-five-glrt-pss-tle-20260912-v4")
    cs = json.loads((source / "selection.json").read_text())["selected"]
    data = json.loads((source / "fractional-glrt-comparison.json").read_text())
    colors = plt.get_cmap("tab10").colors
    lanes = ["native25", "derived2p5", "recorded2p5"]
    records = []
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    for r in data:
        ci = next(i for i, c in enumerate(cs) if c["capture_id"] == r["capture_id"])
        c = cs[ci]
        col = lanes.index(r["lane"])
        start = c["recorded_start_s" if col == 2 else "native_start_s"]
        rate = 25e6 if col == 0 else 2.5e6
        t, y = np.array(r["time_s"]), np.array(r["value"])
        frame = np.rint(((t + start) - y * 1e-9) * 750).astype(int)
        fit = fit_bias(t, y, frame, rate)
        tr = fit["train"]
        baseline = y - fit["baseline"]
        after = y - fit["corrected_prediction"]
        brms = float(np.sqrt(np.mean(baseline[~tr] ** 2)))
        arms = float(np.sqrt(np.mean(after[~tr] ** 2)))
        record = dict(
            capture_id=r["capture_id"],
            lane=r["lane"],
            sample_rate_hz=rate,
            training_count=int(tr.sum()),
            late_count=int((~tr).sum()),
            late_baseline_rms_ns=brms,
            late_periodic_model_rms_ns=arms,
            sine_cosine_coefficients_ns=fit["coefficients"][3:].tolist(),
            fundamental_amplitude_ns=float(np.hypot(*fit["coefficients"][3:5])),
            time_s=t.tolist(),
            predicted_sample_phase=fit["phase"].tolist(),
            baseline_residual_ns=baseline.tolist(),
            periodic_model_residual_ns=after.tolist(),
        )
        records.append(record)
        axes[0, col].scatter(
            fit["phase"][tr],
            (y - fit["smooth"])[tr],
            s=7,
            alpha=0.35,
            color=colors[ci],
            label=c["capture_id"][-6:],
        )
        grid = np.linspace(0, 1, 201)
        phi = 2 * np.pi * grid
        b = (
            np.array([np.sin(phi), np.cos(phi), np.sin(2 * phi), np.cos(2 * phi)]).T
            @ fit["coefficients"][3:]
        )
        axes[0, col].plot(grid, b, color=colors[ci], alpha=0.8)
        axes[1, col].bar(
            ci - 0.17,
            brms,
            width=0.32,
            color="#999999",
            label="Quadratic only" if ci == 0 else None,
        )
        axes[1, col].bar(
            ci + 0.17,
            arms,
            width=0.32,
            color="#157f91",
            label="+ sample-phase model" if ci == 0 else None,
        )
    for col, label in enumerate(
        [
            "25 MS/s native · 40 ns/sample",
            "2.5 MS/s downsampled · 400 ns/sample",
            "2.5 MS/s other radio · 400 ns/sample",
        ]
    ):
        axes[0, col].set_title(label)
        axes[0, col].set_xlabel("Predicted fractional position within one sample")
        axes[0, col].set_ylabel("Training timing residual after smooth fit (ns)")
        axes[0, col].set_ylim(-70, 70)
        axes[1, col].set_xticks(range(5), [c["capture_id"][-6:] for c in cs], rotation=25)
        axes[1, col].set_ylabel("Untouched late-observation residual RMS (ns)")
        axes[1, col].set_title("Fit first 60%; evaluate last 40% without refitting")
        for row in (0, 1):
            axes[row, col].grid(alpha=0.2)
    axes[0, 0].legend(fontsize=7)
    axes[1, 0].legend(fontsize=8)
    fig.suptitle(
        "Fractional GLRT has a smaller, different pattern: sample-phase bias at 2.5 MS/s\n"
        "Two Fourier harmonics plus smooth timing; "
        "improved prediction residual is not calibrated absolute timing accuracy",
        fontsize=12,
    )
    fig.savefig(out / "glrt-sample-phase-bias.png", dpi=150)
    plt.close(fig)
    (out / "glrt-sample-phase-bias.json").write_text(
        json.dumps(
            dict(
                records=records,
                protocol="First 60% only fits baseline and periodic model; last 40% untouched. "
                "Sample phase comes from early-only prediction. "
                "Conditional diagnostic, no absolute truth.",
            ),
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
