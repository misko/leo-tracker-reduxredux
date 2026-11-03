"""Static diagnostic figures for sealed Gaussian-sum receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np

from evaluator import _enu_from_latlon, mixture_density


def _components(items):
    return [(float(item["weight"]), np.asarray(item["mean"][:2], float),
             np.asarray(item["covariance"], float)[:2, :2],
             tuple(item.get("identity_history", ()))) for item in items]


def density_grid(*mixtures, resolution=241):
    all_components = [component for mixture in mixtures for component in mixture]
    means = np.stack([item[1] for item in all_components])
    sigmas = np.stack([np.sqrt(np.diag(item[2])) for item in all_components])
    lower, upper = (means - 4 * sigmas).min(axis=0), (means + 4 * sigmas).max(axis=0)
    east, north = np.linspace(lower[0], upper[0], resolution), np.linspace(lower[1], upper[1], resolution)
    ee, nn = np.meshgrid(east, north)
    points = np.stack((ee, nn), axis=-1)
    return east, north, [mixture_density(points, mixture) for mixture in mixtures]


def timeline_arrays(receipt):
    checkpoints = receipt.get("checkpoints", [])
    labels = sorted({label for row in checkpoints for label, _ in row.get("top_associations", [])})
    association = {label: np.array([dict(row.get("top_associations", [])).get(label, np.nan) for row in checkpoints]) for label in labels}
    return {
        "factor": np.array([row["factor"] for row in checkpoints], dtype=int),
        "background": np.array([row["background_probability"] for row in checkpoints]),
        "retained": np.array([row["retained_mass"] for row in checkpoints]),
        "association": association,
    }


def ranked_associations(timeline, limit=5):
    """Rank reported associations by their largest finite checkpoint probability."""
    return sorted(
        timeline["association"],
        key=lambda label: (-float(np.nanmax(timeline["association"][label])), label),
    )[:limit]


def make_figures(receipt, output_directory):
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    status = receipt.get("status", "unknown")
    diagnostic = status != "complete"
    qualifier = "DIAGNOSTIC — NOT ACCEPTED" if diagnostic else "accepted bounded replay"
    paths = []

    if receipt.get("checkpoints"):
        prior = _components(receipt["initial_components"])
        first = _components(receipt["checkpoints"][0]["components"])
        east, north, densities = density_grid(prior, first)
        fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True, sharex=True, sharey=True)
        vmax = max(float(d.max()) for d in densities)
        levels = np.linspace(0., vmax, 25)
        for axis, density, title in zip(axes, densities, ("Regional prior", "After first completed track"), strict=True):
            image = axis.contourf(east, north, density, levels=levels, cmap="viridis")
            axis.set(title=title, xlabel="East (km)", ylabel="North (km)", aspect="equal")
        fig.colorbar(image, ax=axes, label="location density (km⁻²)")
        fig.suptitle(f"{receipt['unit_id']} {receipt['arm']} — {qualifier}")
        path = output_directory / f"{receipt['unit_id']}-{receipt['prior_name']}-{receipt['arm']}-first-density.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path)

        timeline = timeline_arrays(receipt)
        fig, (top, bottom) = plt.subplots(2, 1, figsize=(9, 6), constrained_layout=True, sharex=True)
        top.plot(timeline["factor"], timeline["background"], marker="o", label="background", linewidth=2)
        ranked = ranked_associations(timeline)
        for label in ranked:
            top.plot(timeline["factor"], timeline["association"][label], marker=".", label=f"sat {label}")
        top.set(ylabel="reported top-10 association probability", ylim=(-.02, 1.02))
        top.legend(loc="best", fontsize="small", ncol=2)
        discarded = 1 - timeline["retained"]
        bottom.plot(timeline["factor"], timeline["retained"], marker="o", label="retained")
        bottom.plot(timeline["factor"], discarded, marker="o", label="discarded")
        bottom.axhline(.01, color="tab:red", linestyle="--", label="1% Gaussian-sum gate")
        bottom.set(xlabel="completed-track factor", ylabel="posterior mass", ylim=(-.02, 1.02))
        bottom.legend(loc="best")
        fig.suptitle(f"{receipt['unit_id']} {receipt['arm']} — {qualifier}")
        path = output_directory / f"{receipt['unit_id']}-{receipt['prior_name']}-{receipt['arm']}-association-mass.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path)
    return paths


def make_matched_comparison(gaussian_sum, greedy, prior_only, output_directory, factor=17,
                            reference_latlon=(37.849056280893684, -122.48575489722863)):
    """Compare arms at a common consumed factor plus the complete greedy endpoint."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    gsf_rows = {row["factor"]: row for row in gaussian_sum.get("checkpoints", [])}
    greedy_rows = {row["factor"]: row for row in greedy.get("checkpoints", [])}
    if factor not in gsf_rows or factor not in greedy_rows:
        raise ValueError("both arms must contain the requested matched factor")
    mixtures = [_components(prior_only["components"]), _components(gsf_rows[factor]["components"]),
                _components(greedy_rows[factor]["components"]), _components(greedy["components"])]
    east, north, densities = density_grid(*mixtures)
    titles = ("Prior only", f"Gaussian sum factor {factor}\nDIAGNOSTIC: 13% mass discarded",
              f"Greedy factor {factor}\nmatched diagnostic", "Greedy factor 49\ncomplete baseline")
    fig, axes = plt.subplots(2, 2, figsize=(10, 9), constrained_layout=True, sharex=True, sharey=True)
    vmax = max(float(d.max()) for d in densities)
    vmin = vmax * 1e-5
    levels = np.geomspace(vmin, vmax, 25)
    config = prior_only["config"]["physics"]
    center = (config["prior_center_lat_deg"], config["prior_center_lon_deg"])
    reference_enu = _enu_from_latlon(center, reference_latlon)
    for axis, density, title in zip(axes.flat, densities, titles, strict=True):
        image = axis.contourf(east, north, np.maximum(density, vmin), levels=levels,
                              norm=LogNorm(vmin=vmin, vmax=vmax), cmap="viridis", extend="min")
        axis.scatter([0.], [0.], marker="+", color="white", s=60, linewidth=1.5, label="prior center")
        axis.scatter([reference_enu[0]], [reference_enu[1]], marker="x", color="tab:red", s=45, linewidth=1.5, label="roof reference")
        axis.set(title=title, xlabel="East (km)", ylabel="North (km)", aspect="equal")
    axes.flat[0].legend(loc="lower left", fontsize="small")
    fig.colorbar(image, ax=axes, label="location density (km⁻², logarithmic scale)")
    fig.suptitle(f"{gaussian_sum['unit_id']} regional arms — conditional roof diagnostics only")
    path = output_directory / f"{gaussian_sum['unit_id']}-regional-matched-location-density.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    document = json.loads(args.receipt.read_text())
    for generated in make_figures(document, args.output):
        print(generated)
