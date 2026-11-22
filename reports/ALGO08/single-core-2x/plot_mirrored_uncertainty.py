"""Show the measured local uncertainty and the two truth positions relative to the face."""

import gzip
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km


def plot(measurements, output):
    mirrors = json.loads(gzip.decompress((measurements / "region-mirrors.json.gz").read_bytes()))["sites"]
    outcomes = json.loads((measurements / "mirrored-uncertainty.json").read_bytes())
    historical_key = measurements.parents[1] / "regional-release/scoring-key.json"
    answers = json.loads(historical_key.read_bytes())["answers"].values()
    truth = {row["recording"]: row["truth"] for row in answers if row["condition"] == "containing"}
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.9), sharex=True, sharey=True, layout="constrained")
    for ax, site in zip(axes, ("north", "south"), strict=True):
        outcome = outcomes[site]
        normal = outcome["face_axis"]
        receipt = "north-edge-signed.json" if site == "north" else "south-edge-full-signed.json"
        recording = Path(json.loads((measurements / receipt).read_bytes())["recording"]).name
        for y, (condition, arm) in enumerate((("inside", "c0"), ("inside", "fitted_c"),
                                               ("outside", "c0"), ("outside", "fitted_c"))):
            offer = mirrors[site][condition]
            if outcome["native_sha256"] != offer["native_sha256"]:
                raise ValueError("Waveform mismatch between geometry and likelihood")
            fit = outcome["arms"][arm]["offers"][condition]
            half = offer["offer"]["width_km"] / 2
            clearance = half - abs(fit["estimate_km"][normal])
            ax.errorbar(clearance, y, xerr=fit["ellipse_halfwidth_km"][normal], fmt="o",
                        color="#216d78", elinewidth=2.3, capsize=4,
                        label="Estimate and local 95% ellipse projection" if y == 0 else None)
            actual_clearance = face_clearance_km(offer["offer"], truth[recording])
            ax.scatter(actual_clearance, y, marker="D", color="#b24b18",
                       s=31, zorder=4, label="Known receiver" if y == 0 else None)
        ax.axvline(0, color="#343e51", lw=1.4, ls="--")
        ax.set_title(f"{site.title()} simulation")
        ax.set_xlabel("Distance inside the offered face (km)")
        ax.set_xlim(-3.5, 3.5)
        ax.set_yticks(range(4), ["Inside · fixed zero", "Inside · fitted", "Outside · fixed zero", "Outside · fitted"])
        ax.set_axisbelow(True)
        ax.grid(axis="x", alpha=.18)
        ax.spines[["top", "right", "left"]].set_visible(False)
    axes[0].set_ylim(3.55, -.55)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=2, frameon=False)
    fig.suptitle("Local position uncertainty crosses the search boundary on all four offers", weight="bold")
    fig.savefig(output, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    directory = Path(__file__).resolve().parent
    plot(directory / "measurements", directory / "mirrored-uncertainty.png")
