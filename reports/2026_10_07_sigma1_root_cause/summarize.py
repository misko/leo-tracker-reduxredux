"""Audit root diagnostic receipts and render the conditional likelihood finding."""
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    oracle = json.loads((HERE / "oracle_results.json").read_text())
    profile = json.loads((HERE / "bias_profile_results.json").read_text())
    breakdown = json.loads((HERE / "profile_breakdown.json").read_text())
    assert oracle["status"] == profile["status"] == "complete"
    assert len(oracle["rows"]) == 32 and len(oracle["selections"]) == 16
    assert len(profile["rows"]) == 18
    assert oracle["sigma_s"] == profile["sigma_s"] == 1.
    for row in oracle["rows"] + profile["rows"]:
        assert row["feasible"]
        if row["arm"] == "zero-c":
            assert row["vector"][6] == 0.
    for selected in oracle["selections"]:
        comparable = [r for r in oracle["rows"] if all(r[k] == selected[k] for k in ("case", "basin", "arm", "location"))]
        assert len(comparable) == 2
        assert selected["objective"] == min(r["objective"] for r in comparable)
    deltas = []
    for arm in ("fitted-c", "zero-c"):
        start = next(r for r in profile["rows"] if r["arm"] == arm and r["fraction"] == 0)
        end = next(r for r in profile["rows"] if r["arm"] == arm and r["fraction"] == 1)
        assert start["converged"] and end["converged"]
        deltas.append(dict(arm=arm, **{key: end[key] - start[key] for key in ("objective", "data_nll", "timing_penalty")}))
        blocks = next(r["blocks"] for r in breakdown["rows"] if r["arm"] == arm)
        total = blocks["all"]["reference_minus_wrong_data_nll"]
        assert abs(total - (end["data_nll"] - start["data_nll"])) < 1e-7
        for partition in (("early", "late"), ("rx0", "rx1"), ("channel1", "channel2", "channel3", "channel4")):
            assert abs(sum(blocks[key]["reference_minus_wrong_data_nll"] for key in partition) - total) < 1e-7
    summary = dict(profile_deltas_reference_minus_wrong=deltas,
                   fixed_position_fits=32, stepwise_profile_fits=16,
                   root_fit_elapsed_s=sum(r["elapsed_s"] for r in oracle["rows"])
                   + sum(r.get("elapsed_s", 0) for r in profile["rows"]),
                   oracle_nonconverged_selections=sum(not r["converged"] for r in oracle["selections"]),
                   profile_nonconverged_steps=sum(not r["converged"] for r in profile["rows"]))
    boundary_old = json.loads((HERE.parent / "2026_10_07_bad_sample_options/2139/results.json").read_text())
    boundary_new = json.loads((HERE / "boundary/results.json").read_text())
    reference = np.asarray(oracle["cases"]["2139"]["reference_point_km"])
    geometry = []
    for name, region in boundary_old["basins"].items():
        distance = float(np.linalg.norm(reference - region["center"]))
        geometry.append(dict(basin=name, reference_distance_km=distance, radius_km=region["radius_km"],
                             reference_outside_by_km=distance - region["radius_km"]))
    assert all(r["reference_outside_by_km"] > 0 for r in geometry)
    winner = next(r for r in boundary_new["selections"] if r["domain"] == "expanded" and r["arm"] == "fitted-c")
    known = next(r for r in oracle["selections"] if r["case"] == "2139" and r["location"] == "known_reference"
                 and r["arm"] == "fitted-c" and r["basin"] == winner["basin"])
    assert known["feasible"]
    region = boundary_old["basins"][winner["basin"]]
    assert np.linalg.norm(reference - region["center"]) < max(25., 2 * region["radius_km"])
    known_score = known["objective"] + winner["calibration_penalty"]
    assert known_score < winner["selection_score"]
    summary["boundary_reference_geometry"] = geometry
    summary["boundary_diagnostic_reference_candidate"] = dict(selection_score=known_score, converged=known["converged"],
        expanded_winner_score=winner["selection_score"], improvement=winner["selection_score"] - known_score,
        diagnostic_only=True, feasible_in_expanded_domain=True)
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    colors = ["#2166ac", "#d6604d"]
    x = np.arange(3)
    for index, delta in enumerate(deltas):
        values = [delta[key] for key in ("data_nll", "timing_penalty", "objective")]
        axes[0].bar(x + (index - .5) * .34, values, width=.34, color=colors[index], label=delta["arm"])
    axes[0].set_xticks(x, ["Frequency data", "Timing penalty", "Total objective"])
    axes[0].axhline(0, color="black", lw=.7)
    axes[0].set_ylabel("Reference score minus wrong-location score")
    axes[0].set_title("The data term favors the wrong location")
    axes[0].legend(frameon=False)
    for index, row in enumerate(breakdown["rows"]):
        values = [row["blocks"][f"channel{k}"]["reference_minus_wrong_data_nll"] for k in range(1, 5)]
        axes[1].bar(np.arange(4) + (index - .5) * .34, values, width=.34, color=colors[index])
    axes[1].set_xticks(np.arange(4), ["Channel 1", "Channel 2", "Channel 3", "Channel 4"])
    axes[1].set_title("That preference spans all four channels")
    axes[1].set_ylabel("Contribution to frequency-data score difference")
    fig.suptitle("12:39 PDT shared-bias capture · relative timing sigma = 1 second", fontsize=14)
    fig.text(.06, .03, "Both endpoint nuisance fits pass stationarity checks; finite-start conditional profiles, not global optima.\n"
             "Same observed windows, satellite bank and frozen calibration. Reference position used only for diagnosis.", fontsize=10)
    fig.subplots_adjust(left=.08, right=.98, bottom=.23, top=.82, wspace=.30)
    fig.savefig(HERE / "likelihood_diagnosis.png", dpi=170)
    fig.savefig(HERE / "likelihood_diagnosis.svg")

    from matplotlib.patches import Circle
    fig, ax = plt.subplots(figsize=(8, 6))
    colors = ["#2166ac", "#d6604d"]
    names = ["point:-106.25:-81.25", "point:-68.75:-106.25"]
    for name, color, label in zip(names, colors, ["Near candidate bank", "Original fitted-c winner bank"]):
        region = boundary_old["basins"][name]
        center, radius = region["center"], region["radius_km"]
        ax.add_patch(Circle(center, radius, facecolor=color, edgecolor=color, alpha=.16))
        ax.add_patch(Circle(center, max(25., 2 * radius), fill=False, edgecolor=color, linestyle="--"))
        ax.plot(*center, marker="+", color=color)
        ax.plot([], [], color=color, label=label)
    ax.scatter(*reference, marker="*", s=200, color="black", label="Known receiver")
    ax.scatter(*winner["vector"][:2], marker="s", s=65, color=colors[0], label="Expanded fitted-c winner")
    old = next(r for r in boundary_old["selections"] if r["option"] == "sigma100" and r["arm"] == "fitted-c")
    ax.scatter(*old["vector"][:2], marker="x", s=65, color=colors[1], label="Original fitted-c winner")
    ax.set(xlim=(-136, -36), ylim=(-138, -45), xlabel="East of regional origin, km", ylabel="North of regional origin, km",
           title="14:39 PDT: original final regions exclude the receiver")
    ax.set_aspect("equal")
    ax.legend(loc="lower left", fontsize=8, framealpha=.95)
    fig.text(.07, .025, "Filled disks: original 12.5 km regions. Dashed: expanded 25 km regions.\n"
             "The two other original regions are farther away and also exclude the reference.", fontsize=9)
    fig.subplots_adjust(bottom=.18, top=.91)
    fig.savefig(HERE / "boundary_geometry.png", dpi=170)
    fig.savefig(HERE / "boundary_geometry.svg")


if __name__ == "__main__":
    main()
