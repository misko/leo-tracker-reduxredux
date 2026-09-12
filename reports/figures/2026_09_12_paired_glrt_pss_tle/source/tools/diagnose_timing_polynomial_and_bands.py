"""Separate polynomial order from PSS repetition branches using early-only fits."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares

ROOT = Path("/srv/bulk/leo/experiments")
LANES = ("native25", "derived2p5", "recorded2p5")
LABELS = ("25 MS/s native", "2.5 MS/s downsampled", "2.5 MS/s independent capture")
COLORS = ("#157f91", "#c76524", "#7d58a0")
REPEAT_NS = 128 / 240e6 * 1e9


def fit_polynomial(t, y, degree):
    """Only observations before 1.35 s can influence a fit or its centering."""
    t, y = np.asarray(t), np.asarray(y)
    train = t < 1.35
    origin = float(np.median(y[train]))
    design = np.vander(t - 0.675, degree + 1)
    coef = np.linalg.lstsq(design[train], y[train] - origin, rcond=None)[0]
    prediction = origin + design @ coef
    residual = y - prediction
    return dict(
        coefficients=coef,
        origin_ns=origin,
        prediction=prediction,
        early_rms_ns=float(np.sqrt(np.mean(residual[train] ** 2))),
        late_rms_ns=float(np.sqrt(np.mean(residual[~train] ** 2))),
    )


def fit_repetition_curve(t, y, degree=2):
    """Fit a smooth curve modulo the known repeat; never declare branch truth."""
    t, y = np.asarray(t), np.asarray(y)
    train = t < 1.35
    baseline = fit_polynomial(t, y, 2)
    residual = y - baseline["prediction"]
    centers, moments = [], []
    for a in np.arange(0, 1.35, 0.1):
        mask = train & (t >= a) & (t < a + 0.1)
        if np.any(mask):
            centers.append(float(np.mean(t[mask] - 0.675)))
            moments.append(np.mean(np.exp(2j * np.pi * residual[mask] / REPEAT_NS)))
    phases = np.unwrap(np.angle(moments)) * REPEAT_NS / (2 * np.pi)
    seed = np.polyfit(centers, phases, degree)
    design = np.vander(t - 0.675, degree + 1)

    def objective(coef):
        angle = 2 * np.pi * (residual[train] - design[train] @ coef) / REPEAT_NS
        return np.r_[np.cos(angle) - 1, np.sin(angle)]

    optimum = least_squares(objective, seed, max_nfev=300, xtol=1e-12, ftol=1e-10, gtol=1e-10)
    if not optimum.success:
        raise ValueError("circular polynomial fit did not converge")
    prediction = baseline["prediction"] + design @ optimum.x
    z = np.exp(2j * np.pi * (y - prediction) / REPEAT_NS)
    folded = np.angle(z) * REPEAT_NS / (2 * np.pi)
    coherence = float(abs(np.mean(z[train])))
    return dict(
        prediction=prediction,
        early_coherence=coherence,
        late_coherence=float(abs(np.mean(z[~train]))),
        supported=coherence >= 0.25,
        late_folded_rms_ns=float(np.sqrt(np.mean(folded[~train] ** 2))),
        residual_ns=y - prediction,
        folded_residual_ns=folded,
        coefficients=optimum.x + np.pad(baseline["coefficients"], (degree - 2, 0)),
        origin_ns=baseline["origin_ns"],
    )


def spacing_scan(t, residual):
    """Exploratory comb-coherence scan; does not identify the physical period."""
    periods = np.arange(350.0, 651.0, 0.5)
    z = np.exp(2j * np.pi * residual[:, None] / periods[None, :])
    moments = []
    for a in np.arange(0, 2.25, 0.125):
        mask = (t >= a) & (t < a + 0.125)
        if np.any(mask):
            moments.append(abs(z[mask].mean(axis=0)))
    coherence = np.mean(moments, axis=0)
    best = int(np.argmax(coherence))
    return dict(
        best_spacing_ns=float(periods[best]),
        peak_coherence=float(coherence[best]),
        periods_ns=periods.tolist(),
        coherence=coherence.tolist(),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output
    if out.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("QNAP is read-only")
    out.mkdir(exist_ok=True)
    v5 = ROOT / "paired-five-pss-outlier-bands-20260912-v5"
    v4 = ROOT / "paired-five-glrt-pss-tle-20260912-v4"
    v2 = ROOT / "paired-five-pss-bandwidth-20260912-v2-fractional"
    selected = json.loads((v4 / "selection.json").read_text())["selected"]
    glrt = json.loads((v4 / "fractional-glrt-comparison.json").read_text())
    pss = json.loads((v2 / "summary.json").read_text())
    previous = json.loads((v5 / "timing-current-status.json").read_text())["residual_records"]
    bias = json.loads((v5 / "glrt-sample-phase-bias.json").read_text())["records"]
    rows = []
    for row, source in enumerate((glrt, pss)):
        for c in selected:
            for lane in LANES:
                r = next(
                    r for r in source if r["capture_id"] == c["capture_id"] and r["lane"] == lane
                )
                t = np.array(r["time_s"])
                y = np.array(r["value"]) if row == 0 else np.array(r["phase_s"]) * 1e9
                if row:
                    t -= c["recorded_start_s" if lane == "recorded2p5" else "native_start_s"]
                fits = {str(degree): fit_polynomial(t, y, degree) for degree in (2, 3)}
                result = dict(
                    capture_id=c["capture_id"],
                    lane=lane,
                    method="PSS" if row else "GLRT",
                    time_s=t,
                    value_ns=y,
                    polynomial=fits,
                )
                if row:
                    result["repetition_curve"] = {
                        str(degree): fit_repetition_curve(t, y, degree) for degree in (2, 3)
                    }
                    old = next(
                        r
                        for r in previous
                        if r["capture_id"] == c["capture_id"]
                        and r["lane"] == lane
                        and r["method"] == "PSS"
                    )
                    result["spacing_scan"] = spacing_scan(t, np.array(old["residual_ns"]))
                rows.append(result)

    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    x = np.arange(5)
    for row, method in enumerate(("GLRT", "PSS")):
        for col, lane in enumerate(LANES):
            subset = [r for r in rows if r["method"] == method and r["lane"] == lane]
            ax = axes[row, col]
            for offset, degree, color in ((-0.17, 2, "#999999"), (0.17, 3, COLORS[col])):
                ax.bar(
                    x + offset,
                    [r["polynomial"][str(degree)]["late_rms_ns"] for r in subset],
                    width=0.32,
                    color=color,
                    label="Quadratic" if degree == 2 else "Cubic",
                )
            ax.set_title(f"{LABELS[col]}\n{method} · all fractional observations")
            ax.set_ylim(0, 210 if row == 0 else 4800)
            ax.set_ylabel("Untouched late-observation residual RMS (ns)")
            ax.set_xticks(x, [c["capture_id"][-6:] for c in selected], rotation=25)
            ax.set_xlabel("Dwell ID suffix")
            ax.grid(axis="y", alpha=0.2)
            ax.set_axisbelow(True)
            ax.legend(fontsize=8)
    worse = sum(
        r["polynomial"]["3"]["late_rms_ns"] > r["polynomial"]["2"]["late_rms_ns"] for r in rows
    )
    fig.suptitle(
        f"Does a cubic fix the residuals? It predicts worse in {worse}/30 series\n"
        "Fit first 60%; evaluate last 40% without refitting or rejecting peaks\n"
        "Same scale within each row; lower training error alone is not evidence for cubic timing",
        fontsize=12,
    )
    fig.savefig(out / "quadratic-versus-cubic.png", dpi=150)
    plt.close(fig)

    # Show the first requested dwell before/after removing different systematic effects.
    capture = selected[0]["capture_id"]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.5), constrained_layout=True)
    for col, lane in enumerate(LANES):
        ax = axes[0, col]
        b = next(r for r in bias if r["capture_id"] == capture and r["lane"] == lane)
        ax.scatter(
            b["time_s"],
            b["baseline_residual_ns"],
            s=13,
            alpha=0.45,
            color="#999999",
            label="Early quadratic only",
        )
        ax.scatter(
            b["time_s"],
            b["periodic_model_residual_ns"],
            s=9,
            alpha=0.7,
            color=COLORS[col],
            label="+ sample-phase bias model",
        )
        ax.set_title(f"{LABELS[col]}\nGLRT · sample-phase correction")
        ax.set_ylim(-110, 110)
        ax.set_ylabel("Measured timing − early-model prediction (ns)")
        ax.legend(fontsize=8, loc="upper left")
        ax = axes[1, col]
        r = next(
            r
            for r in rows
            if r["capture_id"] == capture and r["lane"] == lane and r["method"] == "PSS"
        )
        old = next(
            r
            for r in previous
            if r["capture_id"] == capture and r["lane"] == lane and r["method"] == "PSS"
        )
        ax.scatter(
            r["time_s"],
            old["residual_ns"],
            color="#999999",
            s=5,
            alpha=0.35,
            label="Previous ordinary quadratic residual",
        )
        fit = r["repetition_curve"]["2"]
        ax.scatter(
            r["time_s"],
            fit["residual_ns"],
            color=COLORS[col],
            s=5,
            alpha=0.65,
            label="Quadratic fitted accounting for repeat offsets",
        )
        for k in range(-4, 5):
            ax.axhline(k * REPEAT_NS, color="#333333", alpha=0.3, linestyle="--", linewidth=0.6)
        ax.set_ylim(-3200, 3200)
        ax.set_title(
            "PSS · fit the band family, retain EVERY peak\n"
            "Dashed guides: k × 533.33 ns; no point shifted by k"
        )
        ax.set_ylabel("Measured timing − smooth timing reference (ns)")
        ax.legend(fontsize=7, loc="upper left")
        for row in range(2):
            axes[row, col].axvspan(1.35, 2.25, color="#c3dce9", alpha=0.15)
            axes[row, col].axvline(1.35, color="#555555", linestyle=":", linewidth=1)
            axes[row, col].set_xlim(0, 2.25)
            axes[row, col].set_xlabel("Seconds into interval · shaded area is late evaluation")
            axes[row, col].grid(alpha=0.15)
    fig.suptitle(
        "Systematic effects in dwell 466531: a higher polynomial order is not the common remedy\n"
        "GLRT: fractional sample-phase bias. "
        "PSS: the ordinary fit is pulled by multiple peak branches\n"
        "New models use first 60% only; PSS reference is ambiguous modulo a repeat, "
        "not absolute arrival truth",
        fontsize=12,
    )
    fig.savefig(out / "systematic-bias-six-panels.png", dpi=150)
    plt.close(fig)

    def serialize(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        raise TypeError(type(value).__name__)

    (out / "polynomial-and-bands.json").write_text(
        json.dumps(
            dict(
                records=rows,
                protocol="First 60% fits ordinary and circular polynomials; last 40% evaluates. "
                "Spacing scan is exploratory over whole interval. "
                "Circular residuals are not absolute errors.",
                cubic_worse_series_count=worse,
            ),
            default=serialize,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
