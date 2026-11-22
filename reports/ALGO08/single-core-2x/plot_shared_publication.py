"""Plot matched raw-to-publication timing and score each site independently."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tools.pipeline_eval.scoring import distance_km


HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def main(trial):
    simulations = read(HERE.parent / "regional-release/scoring-key.json")["answers"]
    references = read(HERE.parents[1] / "2026_11_21_ds30_full/reference-audit.json")["cases"]
    roof = next(row for row in references if row["dataset_label"] == "DS30-0016")
    if not roof["authority_eligible"]:
        raise ValueError("Physical recording lacks an eligible survey")
    roof_truth = [roof["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    cases = (("DS30-0016-shared", "DS30-0016 · physical"),
             ("south-shared", "Southern site · simulation"),
             ("north-far-shared", "Northern simulation · true region missing"))
    if trial == "moments":
        cases = (("DS30-0016-deferred", "DS30-0016 · moments and deferred scans"),
                 ("north-edge-moments", "Northern edge · track moments"),
                 ("south-deferred", "Southern site · moments and deferred scans"))
    fig, axes = plt.subplots(len(cases), 2, figsize=(9, 8.2), layout="constrained")
    longest_publication = 0
    for row, (key, site) in enumerate(cases):
        pair = read(HERE / "measurements" / f"{key}.json")
        if key.startswith("DS30-0016"):
            truth = roof_truth
        else:
            recording = Path(pair["recording"]).name
            truths = {tuple(answer["truth"]) for answer in simulations.values() if answer["recording"] == recording}
            if len(truths) != 1:
                raise ValueError("Expected one scoring location for the simulated waveform")
            truth, = truths
        duration, errors = axes[row]
        duration.set_title(site, loc="left", weight="bold")
        for index, (arm, color) in enumerate((("baseline", "#364262"), ("candidate", "#087c67"))):
            run = pair["runs"][arm]
            y = [1.17 - .34 * index, .17 - .34 * index]
            bars = duration.barh(y, [run["elapsed_s"], run["cpu_s"]], height=.29,
                                 color=color, label=arm.capitalize())
            duration.bar_label(bars, fmt="%.1f", padding=3, fontsize=9)
            offsets = [distance_km(run["arms"][k]["latlon"], truth) for k in ("c0", "fitted_c")]
            if any(value is None for value in offsets):
                raise ValueError("This two-fix figure expects published coordinates for both arms")
            errors.scatter(offsets, y, s=32, color=color)
            for x, level in zip(offsets, y):
                errors.annotate(f"{x:.3f}", (x, level), xytext=(6, 0),
                                textcoords="offset points", va="center", fontsize=9)
        duration.set_yticks([1, 0], ["Elapsed", "CPU"])
        errors.set_yticks([1, 0], ["Fixed zero", "Fitted"])
        longest_publication = max(longest_publication, *(run["elapsed_s"] for run in pair["runs"].values()))
        errors.set_xlim(0, 62 if key == "north-far-shared" else 2)
        errors.set_title("Published false fix · expanded distance scale" if key == "north-far-shared"
                         else "Position error on the same recording", loc="left", fontsize=11)
        for ax in (duration, errors):
            ax.set_ylim(-.5, 1.52)
            ax.set_axisbelow(True)
            ax.grid(axis="x", alpha=.15)
            ax.spines[["top", "right", "left"]].set_visible(False)
    for duration in axes[:, 0]:
        duration.set_xlim(0, longest_publication * 1.16)
    axes[-1, 0].set_xlabel("Time from sealed I/Q to web publication (s)")
    axes[-1, 1].set_xlabel("Horizontal error (km)")
    axes[0, 0].legend(loc="upper center", bbox_to_anchor=(.56, 1.49), ncol=2, frameon=False)
    fig.savefig(HERE / f"{trial}-publication.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", choices=("shared", "moments"), default="shared")
    main(parser.parse_args().trial)
