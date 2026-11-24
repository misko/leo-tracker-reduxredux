"""Plot independent position and frequency errors for the paired North comparisons."""

from pathlib import Path

from route_time_ceiling import receipt


def results():
    individual = receipt("whole-stereo-8ms.json.gz")["scores"]["north"]
    group = receipt("cycle-stereo-saved.json.gz")["north_score"]
    split = receipt("per-antenna-held-8ms.json.gz")["score"]["document"]
    return [("ALGO08v3", individual["controls"]["named"]), ("8 ms, all visits", individual["controls"]["all8"]),
            ("8 ms, skip individual visits", individual["candidate"]), ("Same skips, per-antenna choice", split["candidate"]),
            ("8 ms, skip whole cycles", group["candidate"])]


def render(path, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, (position, frequency) = plt.subplots(1, 2, figsize=(10.5, 4), sharey=True)
    fig.subplots_adjust(left=.28, right=.96, bottom=.19, top=.72, wspace=.17)
    fig.suptitle("How skipped visits changed the North fix", x=.035, y=.97, ha="left", weight="bold")
    symbols = [("c0", "Fixed-zero calibration", "o", "#343f73", -.10),
               ("fitted_c", "Fitted calibration", "D", "#007d70", .10)]
    for ax, field, title in [(position, "error_m", "Horizontal position error (m)"), (frequency, "rf_rms_hz", "RF residual RMS (Hz)")]:
        for idx, (_, pair) in enumerate(rows):
            for arm, _, symbol, color, offset in symbols:
                ax.scatter(pair[arm][field], idx+offset, c=color, marker=symbol, s=44, zorder=3)
        ax.set_xlabel(title)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.grid(axis="x", color="#e0e4e9")
        ax.tick_params(axis="y", length=0)
    position.set(xscale="log", yticks=range(len(rows)), yticklabels=[label for label, _ in rows],
                 xticks=(100,300,1000,3000), xticklabels=("100","300","1,000","3,000"))
    position.set_ylim(len(rows)-.55, -.45)
    legend = [Line2D([], [], linestyle="none", marker=s, color=c, label=l) for _,l,s,c,_ in symbols]
    fig.legend(handles=legend, loc="upper left", bbox_to_anchor=(.033, .87), ncol=2, frameon=False)
    fig.savefig(path, dpi=155, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    render(Path(__file__).resolve().parent/"development/receiver-history-north.png", results())
