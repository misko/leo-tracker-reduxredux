"""Summarize wide-prior location experiments without turning scores into confidence."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from diagnose_rx0_position_limits import haversine_km
from replay_regional_doppler import write_json


def map_xy(lat, lon, lat0=39.7392, lon0=-104.9903):
    p, longitude, p0, longitude0 = np.deg2rad([lat, lon, lat0, lon0])
    d = longitude - longitude0
    c = np.arccos(np.clip(np.sin(p0) * np.sin(p) + np.cos(p0) * np.cos(p) * np.cos(d), -1, 1))
    k = c / np.sin(c) if c else 1.0
    return np.array(
        [
            6371.0088 * k * np.cos(p) * np.sin(d),
            6371.0088 * k * (np.cos(p0) * np.sin(p) - np.sin(p0) * np.cos(p) * np.cos(d)),
        ]
    )


def report(base, output):
    output.mkdir(parents=True, exist_ok=True)
    primary = json.loads((base / "conditional-polish.json").read_text())
    models = primary["models"]
    nominal = models[0]
    centre = np.array(nominal["position_km"][:2])
    # Evaluation coordinate from observer configuration; read after solutions seal.
    truth = (37.858988, -122.478103)
    truth_xy = map_xy(*truth)
    rows = []
    for f in sorted((base / "sensitivity").glob("*.json")):
        d = json.loads(f.read_text())
        m = d["models"][0]
        rows.append(
            dict(
                label=f.stem,
                tracks=d["episode_count"],
                **{
                    k: m[k]
                    for k in [
                        "latitude_deg",
                        "longitude_deg",
                        "training_rms_hz",
                        "heldout_rms_hz",
                        "position_km",
                    ]
                },
                reference_error_km=haversine_km((m["latitude_deg"], m["longitude_deg"]), truth),
            )
        )
    fig, axs = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    g = np.load(base / "conditional500/grid.npz")
    score = np.load(base / "conditional500/accumulated.npz")["train"]
    im = axs[0].scatter(
        g["east_km"], g["north_km"], c=np.minimum(score.max() - score, 1000), s=18, cmap="viridis_r"
    )
    fig.colorbar(im, ax=axs[0], label="Composite score loss, clipped at 1,000")
    axs[0].plot(0, 0, "k+", ms=12, label="Denver")
    axs[0].plot(*centre, "r*", ms=14, label="Conditional fit")
    axs[0].set(
        title="9,000 × 9,000 mile prior",
        xlabel="East from Denver (map km)",
        ylabel="North from Denver (map km)",
        aspect="equal",
    )
    axs[0].legend()
    g = np.load(base / "conditional5/grid.npz")
    score = np.load(base / "conditional5/accumulated.npz")["train"]
    local = (np.abs(g["east_km"] - centre[0]) < 35) & (np.abs(g["north_km"] - centre[1]) < 35)
    im = axs[1].scatter(
        g["east_km"][local] - centre[0],
        g["north_km"][local] - centre[1],
        c=np.minimum(score.max() - score[local], 100),
        s=45,
        cmap="viridis_r",
    )
    fig.colorbar(im, ax=axs[1], label="Composite score loss, clipped at 100")
    axs[1].plot(0, 0, "r*", ms=15, label="Continuous nominal fit")
    axs[1].plot(*(truth_xy - centre), "kx", ms=10, label="Configured reference (evaluation only)")
    for r in rows:
        axs[1].plot(*(np.array(r["position_km"][:2]) - centre), "o", ms=4, color="gray")
    axs[1].set(
        title="Local refinement and subset fits",
        xlabel="East relative to estimate (map km)",
        ylabel="North relative to estimate (map km)",
        aspect="equal",
        xlim=(-20, 20),
        ylim=(-20, 20),
    )
    axs[1].legend(fontsize=8)
    fig.suptitle(
        "Location conditioned on strong existing satellite IDs · not an independent blind fix"
    )
    fig.savefig(output / "05-conditional-location-prior-refinement.png", dpi=160)
    plt.close(fig)
    experiments = ["coarse500", "coarse250", "long30-coarse125", "broad500", "fov60-coarse125"]
    available = [n for n in experiments if (base / n / "result.json").exists()]
    fig, axs = plt.subplots(2, 3, figsize=(17, 9), constrained_layout=True)
    results = []
    for ax, name in zip(axs.ravel(), available, strict=False):
        result = json.loads((base / name / "result.json").read_text())
        g = np.load(base / name / "grid.npz")
        score = np.load(base / name / "accumulated.npz")["train"]
        im = ax.scatter(
            g["longitude_deg"],
            g["latitude_deg"],
            c=np.minimum(score.max() - score, 500),
            s=3,
            cmap="viridis_r",
            rasterized=True,
        )
        ax.plot(result["longitude_deg"], result["latitude_deg"], "r*", ms=10)
        ax.set(
            title=name,
            xlabel="Longitude (°)",
            ylabel="Latitude (°)",
            xlim=(-180, 180),
            ylim=(-65, 90),
        )
        ax.grid(alpha=0.2)
        results.append(
            dict(
                name=name,
                **{
                    k: result[k]
                    for k in [
                        "latitude_deg",
                        "longitude_deg",
                        "scan_count",
                        "episode_count",
                        "train_score",
                        "separated_modes",
                    ]
                },
            )
        )
    for ax in axs.ravel()[len(available) :]:
        ax.axis("off")
    fig.suptitle(
        "Catalogue-free-ID searches: model/grid sensitivity\n"
        "Stars are winners, not verified positions"
    )
    fig.savefig(output / "06-wide-search-stability.png", dpi=160)
    plt.close(fig)
    fig, axs = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    for r in rows:
        x, y = np.array(r["position_km"][:2]) - centre
        axs[0].scatter(x, y, s=35)
        axs[0].annotate(r["label"], (x, y), xytext=(4, 4), textcoords="offset points", fontsize=8)
    axs[0].plot(0, 0, "r*", ms=15, label="All strong tracks")
    axs[0].plot(*(truth_xy - centre), "kx", ms=10, label="Configured reference")
    axs[0].set(
        xlabel="East relative to pooled estimate (map km)",
        ylabel="North relative to pooled estimate (map km)",
        aspect="equal",
        title="Rate / 12-hour subset sensitivity",
    )
    axs[0].grid(alpha=0.2)
    axs[0].legend()
    axs[1].barh([r["label"] for r in rows], [r["heldout_rms_hz"] for r in rows])
    axs[1].set(xlabel="Randomized-evaluation RMS (Hz)", title="Residuals at subset-fit locations")
    fig.savefig(output / "07-position-sensitivity.png", dpi=160)
    plt.close(fig)
    summary = dict(
        conditional_position=dict(
            latitude_deg=nominal["latitude_deg"],
            longitude_deg=nominal["longitude_deg"],
            configured_reference_error_km=haversine_km(
                (nominal["latitude_deg"], nominal["longitude_deg"]), truth
            ),
            fit_rms_hz=nominal["training_rms_hz"],
            evaluation_rms_hz=nominal["heldout_rms_hz"],
            tracks=primary["episode_count"],
            points=primary["point_count"],
        ),
        subset_fits=rows,
        wide_searches=results,
        reference_coordinate=truth,
        claim=(
            "Conditional location only; unrestricted catalogue/location inference "
            "has not passed grid/model stability."
        ),
    )
    fov_path = base / "fov-polish.json"
    if fov_path.exists():
        fov = json.loads(fov_path.read_text())
        model = fov["models"][0]
        fov_centre = np.array(model["position_km"][:2])
        fov_rows = []
        for path in sorted((base / "fov-sensitivity").glob("*.json")):
            d = json.loads(path.read_text())
            m = d["models"][0]
            fov_rows.append(
                dict(
                    label=path.stem,
                    tracks=d["episode_count"],
                    **{
                        k: m[k]
                        for k in [
                            "latitude_deg",
                            "longitude_deg",
                            "position_km",
                            "training_rms_hz",
                            "heldout_rms_hz",
                        ]
                    },
                    reference_error_km=haversine_km((m["latitude_deg"], m["longitude_deg"]), truth),
                )
            )
        summary["fov_assisted_position"] = dict(
            latitude_deg=model["latitude_deg"],
            longitude_deg=model["longitude_deg"],
            configured_reference_error_km=haversine_km(
                (model["latitude_deg"], model["longitude_deg"]), truth
            ),
            fit_rms_hz=model["training_rms_hz"],
            evaluation_rms_hz=model["heldout_rms_hz"],
            tracks=fov["episode_count"],
            points=fov["point_count"],
            individual_known_site_ids_used=False,
            known_site_derived_elevation_prior_used=True,
            subset_fits=fov_rows,
        )
        fig, axs = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
        for ax, run, title in zip(
            axs,
            ["fov60-coarse125", "fov1"],
            [
                "FoV-assisted full prior search",
                "Local refinement; configured site used only for evaluation",
            ],
            strict=True,
        ):
            g = np.load(base / run / "grid.npz")
            s = np.load(base / run / "accumulated.npz")["train"]
            if run == "fov1":
                mask = (np.abs(g["east_km"] - fov_centre[0]) < 15) & (
                    np.abs(g["north_km"] - fov_centre[1]) < 15
                )
                x = g["east_km"][mask] - fov_centre[0]
                y = g["north_km"][mask] - fov_centre[1]
                z = np.minimum(s.max() - s[mask], 100)
                im = ax.scatter(x, y, c=z, s=20, cmap="viridis_r")
                fig.colorbar(im, ax=ax, label="Local composite score loss, clipped at 100")
                ax.plot(*(truth_xy - fov_centre), "kx", ms=10, label="Configured reference")
                for r in fov_rows:
                    ax.plot(*(np.array(r["position_km"][:2]) - fov_centre), "o", ms=4, color="gray")
                ax.plot(0, 0, "r*", ms=13, label="Nominal estimate")
                ax.set(
                    xlabel="East relative to estimate (map km)",
                    ylabel="North relative to estimate (map km)",
                )
            else:
                im = ax.scatter(
                    g["east_km"],
                    g["north_km"],
                    c=np.minimum(s.max() - s, 1200),
                    s=3,
                    cmap="viridis_r",
                )
                fig.colorbar(im, ax=ax, label="Composite score loss, clipped at 1,200")
                ax.plot(*fov_centre, "r*", ms=13, label="Refined estimate")
                ax.plot(0, 0, "k+", ms=10, label="Denver")
                ax.set(xlabel="East from Denver (map km)", ylabel="North from Denver (map km)")
            ax.set(title=title, aspect="equal")
            ax.legend(fontsize=8)
        fig.suptitle(
            "Catalogue identities searched anew\n"
            "High-elevation prior learned from existing associations"
        )
        fig.savefig(output / "08-fov-assisted-location.png", dpi=160)
        plt.close(fig)
    write_json(output / "location-summary.json", summary)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    report(a.base, a.output)
