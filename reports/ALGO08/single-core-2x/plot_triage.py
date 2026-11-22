"""Plot publication receipts and score positions against independent reference files."""
from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

from tools.pipeline_eval.scoring import distance_km


HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"
CASES = (
    ("south-baseline-first", "Southern simulation\nbaseline first"),
    ("south-candidate-first", "Southern simulation\ncandidate first"),
    ("DS30-0374", "DS30-0374\ncandidate first"),
    ("north-bursts", "Northern simulation\nburst schedule"),
)


def read(path):
    return json.loads(path.read_bytes())


def main():
    results = {key: read(MEASUREMENTS/(key+".json")) for key, _ in CASES}
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(8.5, 3.5), layout="constrained")
    colors = ["#323c63", "#138273"]
    for index, (key, _) in enumerate(CASES):
        baseline, candidate = (results[key]["runs"][arm] for arm in ("baseline", "candidate"))
        for offset, field, label, color in zip((-.17, .17), ("elapsed_s", "cpu_s"),
                                              ("Elapsed", "Single-core CPU"), colors):
            ratio = candidate[field] / baseline[field]
            bar = ax.bar(index+offset, ratio, .32, label=label if index==0 else None, color=color)
            ax.bar_label(bar, labels=[f"{ratio:.2f}"], padding=2)
        if candidate["receipt"]["decision"] == "withheld":
            ax.text(index, .67, "Lost fix", ha="center", color="#8b361b", weight="bold")
    ax.axhline(.5, color="#a94f20", ls="--", lw=1, label="2× elapsed target")
    ax.set_xticks(range(len(CASES)), [label for _, label in CASES])
    ax.set_ylim(0,1.08)
    ax.set_ylabel("Candidate / baseline time")
    ax.set_title("Raw I/Q to published result", loc="left", weight="bold")
    ax.legend(frameon=False, ncol=3, loc="upper left")
    fig.savefig(HERE/"triage-runtime.png", dpi=175)
    plt.close(fig)

    truth = read(HERE.parent/"regional-release/scoring-key.json")["answers"]
    roof = next(x for x in read(HERE.parents[1]/"2026_11_21_ds30_full/reference-audit.json")["cases"]
                if x["dataset_label"] == "DS30-0374")
    if not roof["authority_eligible"]:
        raise ValueError("Roof recording has no approved scoring reference")
    fig, axes = plt.subplots(2, 3, figsize=(10, 5.4), sharex=True, sharey=True, layout="constrained")
    for col, (key, title) in enumerate([("south-candidate-first", "Southern simulation"),
                                        ("DS30-0374", "DS30-0374 · physical"),
                                        ("north-bursts", "Northern simulation · bursts")]):
        pair = results[key]
        target = ([roof["reference"][k] for k in ("latitude_deg", "longitude_deg")] if key == "DS30-0374"
                  else truth[Path(pair["region"]).stem]["truth"])
        axes[0,col].set_title(title, fontsize=11)
        for row, calibration in enumerate(("c0", "fitted_c")):
            ax = axes[row,col]
            for arm, color, width, style in zip(("baseline", "candidate"), colors, (4, 2), ("-", "--")):
                endpoint = pair["runs"][arm]["arms"][calibration]["latlon"]
                error = distance_km(endpoint, target)
                xs, ys = ([0, error, 2.55], [0, 1, 1]) if error is not None else ([0, 2.55], [0, 0])
                ax.step(xs, ys, where="post", color=color, lw=width, ls=style, label=arm.capitalize())
            ax.set_ylim(-.08, 1.12)
            ax.set_xlim(0, 2.55)
            ax.set_yticks([0, .5, 1])
            ax.yaxis.set_major_formatter(PercentFormatter(1))
            ax.grid(alpha=.2)
    axes[0,0].set_ylabel("Fixed-zero calibration")
    axes[1,0].set_ylabel("Fitted calibration")
    axes[0,0].legend(frameon=False, loc="lower right", fontsize=8)
    fig.supxlabel("Horizontal error (km)")
    fig.suptitle("Fraction of assigned recordings within error · one recording per column", fontsize=13)
    fig.savefig(HERE/"triage-position-error.png", dpi=175)
    plt.close(fig)


if __name__ == "__main__":
    main()
