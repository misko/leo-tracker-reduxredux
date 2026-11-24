"""Remove contiguous held observations while keeping the sealed forecasts fixed."""

import gzip
import json
from itertools import accumulate
from math import fsum, isclose, isfinite
from pathlib import Path


HERE = Path(__file__).resolve().parent


def interval_sensitivity(scores, widths=(1, 2, 3)):
    by_block = {int(index): weight for index, weight in scores["blocks"].items()}
    total = scores["first_minus_second_nats"]
    if (not by_block or min(by_block) < 0 or not all(map(isfinite, by_block.values()))
            or not isclose(fsum(by_block.values()), total, rel_tol=1e-10, abs_tol=1e-9)):
        raise ValueError("The held time blocks must partition the sealed score")
    radio = scores["by_radio"]
    if set(radio) != {"1", "2"} or not isclose(fsum(radio.values()), total, rel_tol=1e-10, abs_tol=1e-9):
        raise ValueError("Expected a matching two-radio decomposition")
    first, last = min(by_block), max(by_block)
    result = {}
    for width in widths:
        if width < 1 or width >= last - first + 1:
            raise ValueError("Erase a proper, nonempty interval")
        retained = [
            (total - fsum(by_block.get(i, 0.0) for i in range(start, start + width)), start)
            for start in range(first, last - width + 2)
        ]
        weakest, start = min(retained)
        result[str(10 * width)] = dict(minimum=weakest, maximum=max(score for score, _ in retained),
                                       weakest_start_s=10 * start, first_loses=sum(score < 0 for score, _ in retained),
                                       starts=len(retained))
    return result


def plot(cases, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6))
    for ax, (case, item) in zip(axes, cases.items(), strict=True):
        held = item["held-score"]
        for arm, label, color in (("c0", "Zero calibration", "#26547c"), ("fitted_c", "Fitted calibration", "#bd681a")):
            score = held["scores"][arm]
            interval_sensitivity(score)
            blocks = {int(index): value for index, value in score["blocks"].items()}
            times = list(range(min(blocks), max(blocks) + 1))
            end_times = [(i + 1) * 10 for i in times]
            values = list(accumulate(blocks.get(i, 0.0) for i in times))
            ax.step([10 * times[0], *end_times], [0.0, *values], where="post", color=color, lw=2, label=label)
            ax.scatter(end_times[-1], values[-1], color=color, s=22)
        ax.axhline(0, color="#555555", lw=0.6)
        ax.set_title(f"{case}    {held['rivals'][0]} vs {held['rivals'][1]}", loc="left", fontsize=11)
        ax.set_xlabel("Held recording time (s)")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.18)
    axes[0].set_ylabel("Cumulative log score difference (nats)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False)
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    fig.savefig(destination, dpi=165)
    plt.close(fig)


def main():
    with gzip.open(HERE / "measurements/dense-family-holdout-offline.json.gz", "rt") as stream:
        packet = json.load(stream)
    cases = {case: packet[case] for case in ("DS30-0008", "DS30-0057")}
    result = {case: {arm: interval_sensitivity(scores) for arm, scores in item["held-score"]["scores"].items()}
              for case, item in cases.items()}
    plot(cases, HERE / "development/held-frequency-choice.png")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
