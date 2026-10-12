"""Plot the exposed DS20 candidate substitution and protected-join diagnosis."""

import json
from pathlib import Path

import matplotlib
import numpy as np
from continuous_merge_consistency_study import LOCAL, PREVIOUS, REPORT
from continuous_merge_positions import load_prepared
from continuous_merge_study import sha, write

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_bootstrap import observation_subset
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior

matplotlib.use("Agg")
from matplotlib import pyplot as plt

SESSION = "fast-014c72ff95ab599c51ba3b3ec9b92cb8"


def main():
    case = LOCAL / "DS20" / SESSION
    old = PREVIOUS / "local/DS20" / SESSION
    diagnosis_path = case / "positions/point-diagnosis.json"
    point_diagnosis = json.loads(diagnosis_path.read_bytes())
    records = [r for r in point_diagnosis if r["point"] == [-80.0, -80.0]]
    consistent = next(r for r in records if r["policy"]["mode"] == "consistent")
    conflict = next(
        d for d in consistent["decisions"] if d["reason"] == "different-orbital-candidate"
    )
    prepared = load_prepared(old / "baseline.json")
    joined = tuple(conflict["joined_rows"])
    parent = prepared.bootstrap_tracks[conflict["parent_indices"][0]]
    obs = observation_subset(prepared.observations, joined)
    in_parent = np.array([r in parent for r in joined])
    with np.load(case / "positions/bank.npz") as z:
        bank = PositionOrbitBank(**{k: z[k] for k in z.files})
    # This audit uses every retained joined observation. Its RMS is explicitly
    # distinct from the bootstrap's 12-point shape statistic.
    measured = np.unwrap(obs.measured_hz * 2 * np.pi / ALIAS_HZ) * ALIAS_HZ / (2 * np.pi)
    fits = []
    for number in (69466, 54102):
        index = int(np.flatnonzero(bank.numbers == number)[0])
        selected = bank.select([index])
        choices = []
        for timing in np.arange(-20.0, 20.001, 2.0):
            predicted = predict_orbits(
                selected, obs, RegionalPrior(), [-80, -80], [timing], derivatives=False
            )[0][:, 0]
            residual = measured - predicted
            offset = np.median(residual)
            for _ in range(10):
                weight = 1 / np.sqrt(1 + ((residual - offset) / 200) ** 2)
                updated = np.sum(weight * residual) / weight.sum()
                if abs(updated - offset) < 0.01:
                    offset = updated
                    break
                offset = updated
            centered = residual - offset
            cost = float(np.mean(2 * 200**2 * (np.sqrt(1 + (centered / 200) ** 2) - 1)))
            choices.append((cost, abs(timing), timing, predicted + offset, centered))
        cost, _, timing, prediction, residual = min(choices, key=lambda v: v[:3])
        fits.append(
            {
                "catalogue_candidate": number,
                "timing_s": float(timing),
                "shape_cost": cost,
                "all_window_rms_hz": float(np.sqrt(np.mean(residual**2))),
                "prediction_hz": prediction,
                "residual_hz": residual,
            }
        )
    fig, axes = plt.subplots(3, 1, figsize=(11, 11), constrained_layout=True)
    for mask, color, label in (
        (~in_parent, "#e17c19", "Added earlier segment"),
        (in_parent, "#1478b5", "Original selected CH4 RX1 segment"),
    ):
        axes[0].scatter(obs.times_s[mask], measured[mask] / 1000, color=color, s=35, label=label)
    colors = ("#267c45", "#9d4082")
    for fit, color in zip(fits, colors, strict=True):
        label = f"Candidate {fit['catalogue_candidate']}, profiled timing {fit['timing_s']:+.0f} s"
        axes[0].plot(obs.times_s, fit["prediction_hz"] / 1000, color=color, label=label)
        axes[1].plot(obs.times_s, fit["residual_hz"], ".-", color=color, label=label)
    axes[0].set_ylabel("Unwrapped measured CFO (kHz)")
    axes[0].set_title("Two orbital shapes over the joined CH4 RX1 observations")
    axes[0].legend(fontsize=9)
    axes[1].axhline(0, color="black", lw=1)
    axes[1].set_ylabel("CFO minus orbital shape (Hz)")
    axes[1].set_title("One profiled constant per full joined arc; all retained windows plotted")
    boundary = (obs.times_s[~in_parent].max() + obs.times_s[in_parent].min()) / 2
    for axis in axes[:2]:
        axis.axvline(boundary, color="grey", linestyle=":")
        axis.grid(alpha=0.2)
        axis.set_xlabel("Seconds since capture start")
    methods = (
        "Original",
        "Guarded replacement",
        "Protected, shape only",
        "Protected, orbital agreement",
    )
    candidate_sets = [
        set(records[0]["catalogue_candidates"]),
        set(
            json.loads((old / "positions/posthoc-coarse-bank-comparison.json").read_bytes())[
                "variants"
            ]["replace-guard"]["satellites"]
        ),
        set(next(r for r in records if r["policy"]["mode"] == "shape")["catalogue_candidates"]),
        set(consistent["catalogue_candidates"]),
    ]
    numbers = (62501, 69466, 54102, 66089)
    matrix = np.array([[int(n in pool) for n in numbers] for pool in candidate_sets])
    axes[2].imshow(matrix, cmap="Greens", vmin=0, vmax=1, aspect="auto", alpha=0.65)
    axes[2].set_xticks(np.arange(len(numbers)), [str(n) for n in numbers])
    axes[2].set_yticks(np.arange(len(methods)), methods)
    axes[2].set_xlabel("Catalogue candidate number")
    for i in range(len(methods)):
        for j in range(len(numbers)):
            axes[2].text(j, i, "Retained" if matrix[i, j] else "Absent", ha="center", va="center")
    axes[2].set_title("Original-candidate preservation at the same exposed grid point")
    fig.suptitle(
        "Why smooth joining can change satellite discovery · DS20 014c\n"
        "Posthoc point east −80 km, north −80 km; never used to seed or restrict the full replays",
        fontsize=13,
    )
    output = REPORT / "candidate-substitution.png"
    fig.savefig(output, dpi=160)
    plt.close(fig)
    write(
        REPORT / "candidate-substitution.json",
        {
            "point": [-80, -80],
            "scope": "Exposed local diagnosis, no satellite identity claim",
            "point_diagnosis_sha256": sha(diagnosis_path),
            "script_sha256": sha(Path(__file__)),
            "image_sha256": sha(output),
            "original_case": str(old),
            "parent_windows": len(parent),
            "joined_windows": len(joined),
            "fits": fits,
            "methods": methods,
            "candidate_numbers": numbers,
            "candidate_retention": matrix,
        },
    )
    write(REPORT / "point-diagnosis.json", point_diagnosis)
    print(
        json.dumps(
            [
                {k: v for k, v in f.items() if k not in ("prediction_hz", "residual_hz")}
                for f in fits
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
