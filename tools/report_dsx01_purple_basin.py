"""Plot the saved purple-basin diagnostics; GPS is evaluated only here."""

import json

import matplotlib
import numpy as np
from debug_dsx01_purple_basin import ARMS, FAMILY, OUTPUT, SOURCE, STARTS, problem
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_continuous_position import CENTER, latlon
from run_dsx01_clean_region import load_scan

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REFERENCE = (37.849061591561885, -122.48574968092912)
COLORS = {0: "firebrick", 6: "#703c91", 9: "#278b9a"}


def load(name):
    return json.loads((OUTPUT / name).read_text())


def truth_xy():
    return np.array([
        (REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
        (REFERENCE[0] - CENTER[0]) * 111,
    ])


def decorate(axis, title):
    axis.plot(*truth_xy(), "*", color="magenta", ms=10, label="GPS: evaluation only")
    axis.set(
        title=title, xlim=(2.5, 7.5), ylim=(-7.5, 0.25), aspect="equal",
        xlabel="East from regional center (km)", ylabel="North (km)",
    )
    axis.grid(alpha=0.2)


def cross_figure():
    rows = load("cross_branch_fits.json")
    figure, axes = plt.subplots(3, 2, figsize=(10, 13), layout="constrained")
    for row, branch in enumerate(STARTS):
        for column, arm in enumerate(ARMS):
            axis = axes[row, column]
            selected = [r for r in rows if r["branch_from_start"] == branch and r["arm"] == arm]
            for item in selected:
                initial = item["initialization_from_start"]
                path = np.array([p["parameters"][:2] for p in item["fit"]["history"]])
                axis.plot(path[:, 0], path[:, 1], color=COLORS[initial], alpha=0.7)
                axis.scatter(*item["initial_point"], color=COLORS[initial], s=35,
                             label=f"Initialize at S{initial:02d} endpoint")
                axis.scatter(
                    *item["fit"]["parameters"][:2], color=COLORS[initial], marker="X", s=65
                )
            decorate(axis, f"Fixed S{branch:02d} hypothesis / {arm}")
            if selected:
                best = min(selected, key=lambda r: r["fit"]["score"])
                axis.text(0.03, 0.03, f"Lowest reached loss: {best['fit']['score']:.3f}",
                          transform=axis.transAxes, fontsize=8)
    axes[0, 0].legend(fontsize=7)
    figure.suptitle(
        "Changing only position initialization keeps each hypothesis in its own minimum\n"
        "All observations retained; 96 steps per fit; matched c arms; GPS never initializes fits",
        fontsize=10,
    )
    figure.savefig(OUTPUT / "cross_branch_convergence.png", dpi=160)
    plt.close(figure)


def surface_figure():
    data = load("conditional_surfaces.json")
    cross = load("cross_branch_fits.json")
    original = {
        i: json.loads((SOURCE / "normal" / f"start_{i:02d}/result.json").read_text())
        for i in STARTS
    }
    figure, axes = plt.subplots(3, 2, figsize=(12, 13), layout="constrained")
    for row, branch in enumerate(STARTS):
        for col, arm in enumerate(ARMS):
            axis = axes[row, col]
            values = next(r["loss"] for r in data["surfaces"]
                          if r["branch_from_start"] == branch and r["arm"] == arm)
            values = np.array(values).reshape(len(data["north"]), len(data["east"]))
            fits = [r["fit"] for r in cross if r["branch_from_start"] == branch and r["arm"] == arm]
            minimum = min(values.min(), *(r["score"] for r in fits))
            mesh = axis.pcolormesh(data["east"], data["north"],
                                   np.log1p(np.maximum(0, values - minimum)),
                                   shading="nearest", cmap="viridis")
            figure.colorbar(mesh, ax=axis, shrink=0.7, label="log(1 + loss above branch minimum)")
            for i in STARTS:
                xy = original[i]["arms"][arm]["endpoint_east_north_km"]
                axis.scatter(*xy, marker="X", c=COLORS[i], edgecolors="white", s=65,
                             label=f"Saved S{i:02d} endpoint")
            axis.plot(*truth_xy(), "*", color="magenta", ms=10, label="GPS: evaluation only")
            axis.set(title=f"S{branch:02d} satellite hypothesis / {arm}", aspect="equal",
                     xlabel="East (km)", ylabel="North (km)")
    axes[0, 0].legend(fontsize=7)
    figure.suptitle(
        "Each assignment hypothesis defines a different conditional loss surface\n"
        "Same 2,909 observations and priors; corrections recomputed on a 1 km diagnostic grid",
        fontsize=10,
    )
    figure.savefig(OUTPUT / "different_conditional_surfaces.png", dpi=160)
    plt.close(figure)


def swap_figure():
    rows = load("controlled_family_swap.json")
    figure, axes = plt.subplots(1, 2, figsize=(12, 8), layout="constrained")
    for axis, arm in zip(axes, ARMS, strict=True):
        for branch in (6, 9):
            for init in (0, 6):
                selected = [r for r in rows if r["recipient_branch"] == branch
                            and r["initialization_from_start"] == init and r["arm"] == arm]
                before = next(r for r in selected if not r["family_swapped_from_S00"])
                after = next(r for r in selected if r["family_swapped_from_S00"])
                a, b = np.array(before["fit"]["parameters"]), np.array(after["fit"]["parameters"])
                axis.annotate("", xy=b, xytext=a,
                              arrowprops=dict(arrowstyle="->", color=COLORS[branch], alpha=0.6))
                axis.scatter(*a, color=COLORS[branch], marker="o", s=55)
                axis.scatter(*b, color=COLORS[branch], marker="X", s=70)
                if init == 0:
                    axis.annotate(f"S{branch:02d}: 60727", a, xytext=(7, 10),
                                  textcoords="offset points", fontsize=8, color=COLORS[branch])
                    axis.annotate(f"S{branch:02d}: 100320", b, xytext=(7, -12),
                                  textcoords="offset points", fontsize=8, color=COLORS[branch])
        decorate(axis, arm)
    figure.suptitle(
        "Controlled intervention: replace only three RX2 satellite labels (141 points)\n"
        "Identical data, aliases and priors; zero phase expansion references for every branch\n"
        "Circles: original labels; X: replacement labels. "
        "Arrows compare endpoints, not descent steps.",
        fontsize=10,
    )
    figure.savefig(OUTPUT / "three_fragment_label_intervention.png", dpi=160)
    plt.close(figure)


def residual_figure():
    scan, sigma = load_scan("DSX01-S01")
    predictions, tracks = {}, {}
    for i in (0, 6):
        source = json.loads((SOURCE / "normal" / f"start_{i:02d}/result.json").read_text())
        p = problem(scan, sigma, source["final_node"], "c0")
        calculated = p.calculate(np.array(source["arms"]["c0"]["fit"]["parameters"]))
        for member, row, sl in zip(p.members, p.rows, p.slices, strict=True):
            if row["component"] in FAMILY:
                tracks[row["component"]] = scan.tracks[member]
                predictions[i, row["component"]] = dict(
                    values=p.values[sl], residual=calculated["conditional_residual_hz"][sl],
                    prediction=p.values[sl] - calculated["conditional_residual_hz"][sl],
                )
    figure, axes = plt.subplots(3, 2, figsize=(13, 10), layout="constrained")
    for index, component in enumerate(FAMILY):
        track = tracks[component]
        values = predictions[0, component]["values"]
        baseline = values.mean()
        axes[index, 0].scatter(track["times"], values - baseline, c="black", s=10, label="GLRT CFO")
        for i in (0, 6):
            predicted = predictions[i, component]
            label = f"S{i:02d} / satellite {100320 if i == 0 else 60727}"
            axes[index, 0].plot(track["times"], predicted["prediction"] - baseline,
                                color=COLORS[i], label=label)
            axes[index, 1].plot(track["times"], predicted["residual"], ".-",
                                color=COLORS[i], ms=4, label=label)
        axes[index, 0].set(
            title=f"{component}: {len(values)} points", ylabel="CFO − fragment mean (Hz)"
        )
        axes[index, 1].axhline(0, color="black", lw=0.5)
        axes[index, 1].set(title="Conditional residual", ylabel="Hz")
        for axis in axes[index]:
            axis.set_xlabel("Time in scan (s)")
            axis.grid(alpha=0.2)
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].legend(fontsize=8)
    figure.suptitle(
        "Two satellites can fit short fragments after shared radio/orbit corrections\n"
        "Predictions include receiver, orbital and fragment corrections at each branch endpoint",
        fontsize=10,
    )
    figure.savefig(OUTPUT / "ambiguous_family_GLRT_and_residuals.png", dpi=160)
    plt.close(figure)


def extension_figure():
    paths = {i: OUTPUT / f"eight_round_extension_S{i:02d}.json" for i in STARTS}
    if not all(p.exists() for p in paths.values()):
        return
    figure, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for i, path in paths.items():
        source = json.loads(path.read_text())
        for arm in ARMS:
            fits = [r["fits"][arm] for r in source["rounds"]]
            errors = [distance_km(latlon(r["parameters"]), REFERENCE) for r in fits]
            drift = [np.mean(np.array(r["state"]["beta"])[6:8]) / 150 for r in fits]
            for axis, values in zip(axes, (errors, drift), strict=True):
                axis.plot(
                    np.arange(1, len(fits) + 1), values,
                    "o-" if arm == "c0" else "x--", color=COLORS[i], ms=4,
                    label=f"S{i:02d} / {arm}",
                )
    axes[0].set(ylabel="Position error (km), GPS evaluation only")
    axes[1].set(ylabel="RX2 mean fitted drift (Hz/s)")
    for axis in axes:
        axis.set_xlabel("Association / position round")
        axis.grid(alpha=0.2)
    axes[0].legend(fontsize=8)
    figure.suptitle(
        "Eight outer rounds do not escape the alternate family hypothesis\n"
        "Matched observations, candidates and c-arm budgets; drift is model-inferred",
        fontsize=10,
    )
    figure.savefig(OUTPUT / "eight_round_position_and_drift.png", dpi=160)
    plt.close(figure)


def proposal_figure():
    path = OUTPUT / "family_subset_scores.json"
    if not path.exists():
        return
    rows = json.loads(path.read_text())
    figure, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    for axis, branch in zip(axes, (6, 9), strict=True):
        for arm_index, arm in enumerate(ARMS):
            selected = [r for r in rows if r["recipient_branch"] == branch
                        and r["arm"] == arm and not r["common_zero_phase_reference"]]
            baseline = next(r["score"] for r in selected if not r["changed_count"])
            selected = [r for r in selected if r["changed_count"]]
            names = ["+".join(k.split("-")[-2] for k in r["components_swapped"])
                     for r in selected]
            axis.bar(np.arange(len(selected)) + (arm_index - 0.5) * 0.35,
                     [r["score"] - baseline for r in selected], width=0.35, label=arm)
        axis.axhline(0, color="black", lw=0.8)
        axis.set(title=f"S{branch:02d}: position held at purple endpoint",
                 ylabel="Loss change after label replacement (lower is better)")
        axis.set_xticks(np.arange(len(names)), names, rotation=40, ha="right")
        axis.grid(axis="y", alpha=0.2)
    axes[0].legend()
    figure.suptitle(
        "The final objective already prefers replacements omitted by the proposal stage\n"
        "Selected RX2 fragments relabeled 60727 → 100320; identical data, aliases and priors",
        fontsize=10,
    )
    figure.savefig(OUTPUT / "missed_improving_proposals.png", dpi=160)
    plt.close(figure)


def run():
    cross_figure()
    swap_figure()
    if (OUTPUT / "conditional_surfaces.json").exists():
        surface_figure()
    residual_figure()
    extension_figure()
    proposal_figure()
    rows = load("all_start_comparison.json")
    for row in rows:
        row["position_error_km"] = distance_km(latlon(row["endpoint"]), REFERENCE)
    (OUTPUT / "postfit_evaluation.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    run()
