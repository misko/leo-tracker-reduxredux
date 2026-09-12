"""Describe fixed-candidate PSS outliers; band folding is diagnostic, not truth."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output
    if out.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("QNAP is read-only")
    out.mkdir(exist_ok=True)
    source = Path("/srv/bulk/leo/experiments/paired-five-pss-bandwidth-20260912-v3-causal-lock")
    selection = json.loads(
        (
            source.parent / "paired-five-pss-bandwidth-20260912-v2-fractional/selection.json"
        ).read_text()
    )["selected"]
    period = 128 / 240e6 * 1e9
    records, pooled = [], []
    fig, axes = plt.subplots(5, 3, figsize=(16, 14), constrained_layout=True)
    for row, c in enumerate(selection):
        path = source / (c["capture_id"] + ".json")
        ds = [d for d in json.loads(path.read_text())["decisions"] if d["innovation_s"] is not None]
        r = np.array([d["innovation_s"] * 1e9 for d in ds])
        t = np.array([d["time_s"] - c["native_start_s"] for d in ds])
        rejected = abs(r) > 120
        k = np.rint(r / period).astype(int)
        folded = r - k * period
        near = rejected & (abs(folded) <= 20)
        band_rows = [
            dict(
                multiple=int(i),
                count=int(np.sum(rejected & (k == i))),
                median_residual_ns=float(np.median(r[rejected & (k == i)])),
                folded_rms_ns=float(np.sqrt(np.mean(folded[rejected & (k == i)] ** 2))),
            )
            for i in np.unique(k[rejected])
        ]
        starts = np.flatnonzero(rejected & ~np.r_[False, rejected[:-1]])
        stops = np.flatnonzero(rejected & ~np.r_[rejected[1:], False])
        rec = dict(
            capture_id=c["capture_id"],
            source=str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            predicted_frame_count=len(r),
            large_outlier_count=int(rejected.sum()),
            near_repeat_count=int(near.sum()),
            fraction_near_repeat=float(near.sum() / rejected.sum()),
            outlier_run_count=len(starts),
            longest_consecutive_outlier_run=int(max(stops - starts + 1)),
            folded_all_outlier_rms_ns=float(np.sqrt(np.mean(folded[rejected] ** 2))),
            near_repeat_folded_rms_ns=float(np.sqrt(np.mean(folded[near] ** 2))),
            outliers_per_250ms_block=[
                int(np.sum(rejected & (t >= b * 0.25) & (t < (b + 1) * 0.25))) for b in range(9)
            ],
            bands=band_rows,
            time_s=t.tolist(),
            innovation_ns=r.tolist(),
            folded_ns=folded.tolist(),
        )
        records.append(rec)
        pooled.extend(r[rejected].tolist())
        axes[row, 0].scatter(t[~rejected], r[~rejected], s=2, color="#157f91", alpha=0.35)
        axes[row, 0].scatter(t[rejected], r[rejected], s=6, color="#c76524", alpha=0.7)
        for n in range(-4, 5):
            axes[row, 0].axhline(n * period, color="#7d58a0", lw=0.5, alpha=0.35)
            axes[row, 1].axvline(n * period, color="#7d58a0", lw=0.7, alpha=0.4)
        axes[row, 0].set_ylim(-2300, 2300)
        axes[row, 0].set_ylabel(f"{c['capture_id'][-6:]}\nMeasured − prior prediction (ns)")
        axes[row, 0].set_title(f"{int(rejected.sum())}/{len(r)} large outliers")
        axes[row, 0].set_xlabel("Seconds into selected interval")
        axes[row, 1].hist(r[rejected], bins=np.arange(-2300, 2301, 20), color="#c76524")
        axes[row, 1].set_xlim(-2300, 2300)
        axes[row, 1].set_title("Outlier histogram · lines at k × 533.33 ns")
        axes[row, 1].set_xlabel("Measured − prior prediction (ns)")
        axes[row, 1].set_ylabel("Frames")
        axes[row, 2].hist(folded[rejected], bins=np.arange(-270, 271, 5), color="#c76524")
        axes[row, 2].axvspan(-20, 20, color="#157f91", alpha=0.15)
        axes[row, 2].set_xlim(-270, 270)
        axes[row, 2].set_title(f"{int(near.sum())}/{int(rejected.sum())} within ±20 ns of a repeat")
        axes[row, 2].set_xlabel("Residual after subtracting nearest k × 533.33 ns")
        axes[row, 2].set_ylabel("Frames")
        for ax in axes[row]:
            ax.grid(alpha=0.15)
    total = sum(r["large_outlier_count"] for r in records)
    near = sum(r["near_repeat_count"] for r in records)
    fig.suptitle(
        "Remaining wideband PSS outliers cluster at repetition offsets: "
        f"{near}/{total} ({near / total:.1%}) within ±20 ns\n"
        "Corrected fractional timing · 25 MS/s · "
        "prior predictions use earlier accepted measurements\n"
        "Right column is diagnostic subtraction only; it does not validate corrected timing",
        fontsize=13,
    )
    fig.savefig(out / "pss-outlier-bands-five-dwells.png", dpi=150)
    plt.close(fig)
    r = np.array(pooled)
    folded = r - np.rint(r / period) * period
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), constrained_layout=True)
    axes[0].hist(r, bins=np.arange(-2300, 2301, 10), color="#c76524")
    for n in range(-4, 5):
        axes[0].axvline(n * period, color="#7d58a0", ls="--", lw=0.8)
    axes[0].set_xticks(np.arange(-4, 5) * period, [f"{k}×" for k in range(-4, 5)])
    axes[0].set_xlabel("Timing residual · one repeat = 533.33 ns")
    axes[0].set_ylabel("Outlier frames per 10 ns bin")
    axes[0].set_title(f"{total} large outliers across five dwells")
    axes[1].hist(folded, bins=np.arange(-270, 271, 5), color="#c76524")
    axes[1].axvspan(-20, 20, color="#157f91", alpha=0.15)
    axes[1].set_xlabel("Residual after subtracting nearest repetition multiple (ns)")
    axes[1].set_ylabel("Outlier frames per 5 ns bin")
    axes[1].set_title(f"{near}/{total} ({near / total:.1%}) land within ±20 ns")
    for ax in axes:
        ax.grid(alpha=0.15)
    fig.suptitle(
        "PSS repetition bands remain after fractional-delay correction\n"
        "Diagnostic folding shows structure; "
        "it is not proof that subtracting a band gives the true arrival",
        fontsize=12,
    )
    fig.savefig(out / "pss-outlier-bands-overview.png", dpi=150)
    plt.close(fig)
    summary = dict(
        period_ns=period,
        large_outlier_threshold_ns=120,
        band_tolerance_ns=20,
        large_outlier_count=total,
        near_repeat_count=near,
        records=records,
        status="descriptive conditional-candidate audit; not a validated correction",
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(f"{near}/{total} outliers within 20 ns of {period:.6f} ns multiples")


if __name__ == "__main__":
    main()
