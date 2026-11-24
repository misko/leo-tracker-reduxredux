"""Plot the sealed adjacent-correlation and physical-lag readout."""

import argparse
import gzip
import json
from pathlib import Path


def render(receipt, output):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    values = json.loads(gzip.decompress(receipt.read_bytes()))["cases"]
    order = ("DS30-0274", "DS30-0019", "DS30-0049", "DS30-0016")
    colors = ("#116978", "#7b3c77", "#ac4b2f", "#557227")
    labels = ("0274 independent", "0019 independent", "0049 development", "0016 weak")
    fig = Figure(figsize=(11.4, 4.7), dpi=150, layout="constrained")
    fig.suptitle("Adjacent short-aperture CFO differences on matched carrier tracks", fontweight="bold")
    corr, semi = fig.subplots(1, 2)
    for i,(case,color,label) in enumerate(zip(order,colors,labels,strict=True)):
        q = values[case]["metrics"]["delta_hz"]
        raw = q["raw"][1]
        adjusted = q["detrended"][1]
        lo,hi = q["bootstrap_95"]
        corr.plot(raw,i+.12,marker="o", markerfacecolor="white",markeredgecolor=color)
        corr.errorbar(adjusted,i-.12,xerr=[[adjusted-lo],[hi-adjusted]],fmt="o",color=color,capsize=3)
        semi.plot(range(5),[row["gamma_hz2"] for row in q["variogram"]],marker="o",color=color,label=label)
    corr.set_yticks(range(4), labels=labels)
    corr.invert_yaxis()
    corr.axvline(0,color="#85929a",linestyle="--",linewidth=1)
    corr.set(title="Adjacent same-piece pairs, ≤2 s", xlabel="Pearson correlation")
    corr.plot([],[],marker="o",markerfacecolor="white",markeredgecolor="#444",linestyle="",label="Raw")
    corr.plot([],[],marker="o",color="#444",label="Affine-adjusted with track interval")
    corr.legend(loc="lower left",fontsize=8,frameon=False)
    corr.set_ylim(4.05,-.45)
    semi.set(title="Affine-adjusted signed differences", xlabel="Hardware lag (s)", ylabel="Semivariance (Hz²)")
    semi.set_xticks(range(5),labels=("0–0.5","0.5–1","1–2","2–4","4–8"))
    semi.legend(fontsize=8,frameon=False)
    for ax in (corr,semi):
        ax.spines[["right","top"]].set_visible(False)
        ax.grid(axis="y",alpha=.23)
    FigureCanvasAgg(fig).print_png(output)


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("receipt",type=Path)
    cli.add_argument("output",type=Path)
    args=cli.parse_args()
    render(args.receipt,args.output)
