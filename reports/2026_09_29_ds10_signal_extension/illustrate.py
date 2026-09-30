"""Static scientific figures and raw sign table for the DS10 follow-up."""

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

OUT = Path(__file__).resolve().parent / "local"


def main():
    summaries = json.loads((OUT / "paired-summary.json").read_text())["visits"]
    headers = [(r["name"], r["header"]) for r in summaries if "matched" in r["header"]]
    fig, ax = plt.subplots(figsize=(9, 4.5), layout="constrained")
    for i, (_name, h) in enumerate(headers):
        ax.bar(i - .18, h["matched"]["agreement"], width=.32, color="#237fa3",
               label="Matched receivers" if i == 0 else None)
        ax.errorbar(i + .18, h["shifted_mean"],
                    yerr=[[h["shifted_mean"] - h["shifted_range"][0]],
                          [h["shifted_range"][1] - h["shifted_mean"]]],
                    fmt="o", color="#c56a17", capsize=6,
                    label="Frame mismatch: mean and full range" if i == 0 else None)
        ax.plot(i, h["matched"]["coordinate_baseline"], "x", color="#444444", ms=10,
                label="Per-coordinate bit-bias baseline" if i == 0 else None)
        ax.text(i - .18, h["matched"]["agreement"] + .025,
                f"{h['matched']['count']:,} decisions", ha="center", fontsize=9)
    ax.set(xticks=range(len(headers)),
           xticklabels=[name.replace("DS10-F010-", "") for name, _ in headers],
           ylim=(0, 1), ylabel="Real-sign agreement",
           title="Three DS10 visits: changing early signs reproduce across receivers\n"
           "Symbols 2–7; discovery-fixed masks; later frames evaluated")
    ax.legend(loc="lower right", fontsize=9)
    fig.savefig(OUT / "header-agreement.png", dpi=180)
    plt.close(fig)
    name, h = headers[0]
    grid = []
    with (OUT / "changing-header-signs.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["visit", "frame", "ofdm_symbol", "fft_bin", "rx0", "rx1",
                         "selected", "consensus"])
        for visit_name, header in headers:
            for frame in header["raw_signs"]:
                for symbol in frame["symbols"]:
                    for i, carrier in enumerate(header["bins"]):
                        writer.writerow([visit_name, frame["frame"], symbol["ofdm_symbol"],
                                         carrier, symbol["rx0"][i], symbol["rx1"][i],
                                         symbol["selected"][i], symbol["consensus"][i]])
    for frame in h["raw_signs"]:
        values = []
        for s in frame["symbols"]:
            values.extend(-1 if selected == "0" else 2 if a != b else int(a)
                          for a, b, selected in zip(s["rx0"], s["rx1"], s["selected"],
                                                    strict=True))
        grid.append(values)
    fig, ax = plt.subplots(figsize=(13, 5), layout="constrained")
    im = ax.imshow(np.array(grid), aspect="auto", interpolation="nearest", vmin=-1, vmax=2,
                   cmap=ListedColormap(["#dddddd", "#285aa3", "#26a899", "#e98b31"]))
    n = len(h["bins"])
    ax.set(xticks=[n * i + (n - 1) / 2 for i in range(6)],
           xticklabels=[f"OFDM {i}" for i in range(2, 8)],
           xlabel="28 non-pilot carriers per OFDM symbol; these are not byte boundaries",
           ylabel="Held-out evaluation frames", title=f"{name}: observed early-region signs")
    for i in range(1, 6):
        ax.axvline(n * i - .5, color="white", lw=1)
    bar = fig.colorbar(im, ax=ax, ticks=[-1, 0, 1, 2], shrink=.8)
    bar.ax.set_yticklabels(["Excluded", "Both RX: 0", "Both RX: 1", "RX disagree"])
    fig.savefig(OUT / "changing-header-signs.png", dpi=180)
    plt.close(fig)
    summary = json.loads((OUT / "correlation-summary.json").read_text())
    state = next(r for r in summary["state_summaries"] if r["cross_session"])
    fig, ax = plt.subplots(figsize=(9, 4.5), layout="constrained")
    x = np.arange(4)
    for key, shift, color, label in [("same", -.18, "#237fa3", "Shared accepted tail state"),
                                      ("different", .18, "#c56a17", "No shared tail state")]:
        ax.bar(x + shift, [r.get("mean", np.nan) for r in state[key]], width=.32,
               color=color, label=label)
    ax.set(xticks=x, xticklabels=["2–7", "8–33", "34–129", "130–193"],
           xlabel="OFDM symbol region", ylabel="Mean normalized phase-profile correlation",
           title="Cross-session comparisons involving DS10\n"
           "Same edge/channel; descriptive dependent pairs, not an identity test")
    ax.axhline(0, color="black", lw=.6)
    ax.legend()
    fig.savefig(OUT / "state-conditioned-correlations.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
