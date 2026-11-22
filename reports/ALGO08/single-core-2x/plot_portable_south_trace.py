"""Plot solver positions in the supplied regional frame after public scoring."""
import argparse
import gzip
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from tools.pipeline_eval.qualification.score_paired_holdout import offset_km


def plot(trace, scored, output):
    case, = (row for row in scored["rows"] if row["case"] == trace["plan"]["case"]
             and row["mode"] == trace["plan"]["mode"])
    if case["offer"] != trace["plan"]["offer"] or case["document_sha256"] != trace["plan"]["document_sha256"]:
        raise ValueError("Trace and scoring reference must use the same detections and region")
    east, north = case["reference_east_north_km"]
    restored = case.get("builds", {}).get("complete_family_cavity")
    runs = trace["results"]
    fig, axes = plt.subplots(1, 2, figsize=(8.8, 5.3), sharex=True, sharey=True, layout="constrained")
    fig.get_layout_engine().set(h_pad=.12, w_pad=.08)
    for ax, arm, title in zip(axes, ("c0", "fitted_c"), ("Fixed-zero calibration", "Fitted calibration"), strict=True):
        def point(build, stage):
            x, y = runs[build]["stages"][stage]["arms"][arm]["endpoint"]
            return x - east, y - north

        before = point("installed", "signed")
        after = point("installed", "cavity")
        approximate = point("covariance", "signed")
        ax.axhline(0, lw=.75, color="#bbbec2")
        ax.axvline(0, lw=.75, color="#bbbec2")
        ax.annotate("", xy=after, xytext=before, arrowprops=dict(arrowstyle="-|>", color="#42537a",
                                                                  lw=1.5, shrinkA=6, shrinkB=9))
        ax.scatter(*before, marker="o", facecolors="white", edgecolors="#42537a", s=72,
                   label="Deployed, before reassignment", zorder=3)
        ax.scatter(*after, marker="o", color="#42537a", s=72, label="Deployed, published", zorder=3)
        ax.scatter(*approximate, marker="s", color="#008169", s=60, label="Optimized, published", zorder=3)
        if restored is not None:
            x, y = offset_km(case["offer"], restored["arms"][arm]["latlon"])
            corrected = x - east, y - north
            ax.annotate("", xy=corrected, xytext=approximate,
                        arrowprops=dict(arrowstyle="-|>", color="#b15a19", lw=1.2,
                                        ls="--", shrinkA=6, shrinkB=8))
            ax.scatter(*corrected, marker="^", color="#b15a19", s=72,
                       label="Optimized, reassignment restored", zorder=3)
        ax.scatter(0, 0, marker="*", color="#222222", s=160, label="Simulated receiver", zorder=4)
        ax.set(aspect="equal", xlabel="East of receiver (km)", title=title)
        ax.margins(.22)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("North of receiver (km)")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="outside lower center", ncol=2, frameon=False)
    fig.suptitle("Satellite reassignment on the southern African simulation", weight="bold", fontsize=14)
    fig.savefig(output, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("trace", "scored", "output"):
        cli.add_argument(name, type=Path)
    args = cli.parse_args()
    data = args.trace.read_bytes()
    if args.trace.suffix == ".gz":
        data = gzip.decompress(data)
    plot(json.loads(data), json.loads(args.scored.read_bytes()), args.output)
