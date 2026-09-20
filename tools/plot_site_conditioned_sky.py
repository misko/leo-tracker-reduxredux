"""Empirical sky support from archived TLE candidates, explicitly site-conditioned."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from diagnose_rx0_position_limits import local_basis, sky_angle
from replay_regional_doppler import state_arrays, write_json

from leo.sky.frames import geodetic_to_ecef_km
from leo.sky.propagation import parse_element_sets


def sky_axis(ax):
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 90)
    ax.set_yticks([0, 30, 60, 90], ["90°", "60°", "30°", "0°"])
    ax.grid(alpha=0.3)


def render(evidence, reviews_path, output):
    output.mkdir(parents=True, exist_ok=True)
    reviews = json.loads(reviews_path.read_text())
    cache = {}
    rows = []
    exposure = []
    seen = set()
    for review in reviews:
        site = review["observer_site"]
        receiver = np.array(
            geodetic_to_ecef_km(site["latitude_deg"], site["longitude_deg"], site["altitude_m"])
        )
        basis = local_basis(site["latitude_deg"], site["longitude_deg"])
        key = review["tle_file"]
        if key not in cache:
            cat = parse_element_sets((evidence / "evidence" / key).read_text())
            cache[key] = (cat, {n: i for i, n in enumerate(cat.satellite_numbers)})
        cat, index = cache[key]
        if review["session_id"] not in seen:
            seen.add(review["session_id"])
            ids = [
                i
                for i, (name, epoch) in enumerate(
                    zip(cat.names, cat.element_epoch_utc_ns(), strict=True)
                )
                if name.startswith("STARLINK")
                and not name.endswith(" DEB")
                and epoch < review["reference_utc_ns"]
            ]
            p, _, _ = state_arrays(
                cat, ids, review["reference_utc_ns"], np.array([149.0, 150.0, 151.0])
            )
            d = p[:, 1] - receiver
            u = d / np.linalg.norm(d, axis=1)[:, None]
            az = np.rad2deg(np.arctan2(u @ basis[0], u @ basis[1])) % 360
            el = np.rad2deg(np.arcsin(np.clip(u @ basis[2], -1, 1)))
            exposure.extend(zip(az[el > 0].tolist(), el[el > 0].tolist(), strict=True))
        first, second = review["candidates"][:2]
        if (
            max(first["fit_rms_hz"], first["randomized_evaluation_rms_hz"]) >= 250
            or second["randomized_evaluation_rms_hz"] <= 2 * first["randomized_evaluation_rms_hz"]
        ):
            continue
        t = np.linspace(review["start_s"], review["end_s"], 13)
        p, _, ids = state_arrays(
            cat,
            [index[first["catalog_number"]]],
            review["reference_utc_ns"],
            t,
            orbit_time_s=first["selected_tau_s"],
        )
        if len(ids) != 1:
            continue
        angles = np.array([sky_angle(v, receiver, basis) for v in p[0]])
        if angles[6, 1] < 0:
            continue
        rows.append(
            dict(
                session_id=review["session_id"],
                tracklet_id=review["tracklet_id"],
                norad=first["catalog_number"],
                rate=review["sample_rate_hz"] / 1e6,
                channel=review["channel"],
                edge=review["edge"],
                span_s=review["end_s"] - review["start_s"],
                az=angles[:, 0].tolist(),
                el=angles[:, 1].tolist(),
                rms=first["randomized_evaluation_rms_hz"],
                runner_rms=second["randomized_evaluation_rms_hz"],
                reference_utc_ns=review["reference_utc_ns"],
            )
        )
    colours = {10: "#2166ac", 15: "#e08214", 20: "#6a3d9a"}
    fig, axs = plt.subplots(1, 3, figsize=(16, 6), subplot_kw={"projection": "polar"})
    for ax, rate in zip(axs, colours, strict=True):
        sky_axis(ax)
        rr = [r for r in rows if r["rate"] == rate]
        for r in rr:
            ax.plot(
                np.deg2rad(r["az"]), 90 - np.array(r["el"]), alpha=0.2, color=colours[rate], lw=0.7
            )
            ax.scatter(
                np.deg2rad(r["az"][6]), 90 - r["el"][6], s=10, alpha=0.5, color=colours[rate]
            )
        ax.set_title(f"{rate:g} MS/s · {len(rr)} candidate tracks")
    fig.suptitle(
        "Empirical heard sky · existing site-conditioned TLE candidates\n"
        "Paths across observed support; dot = track midpoint; not antenna gain"
    )
    fig.savefig(output / "01-heard-sky-polar.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    az = np.array([r["az"][6] for r in rows])
    el = np.array([r["el"][6] for r in rows])
    ex = np.array(exposure)
    ab = np.linspace(0, 360, 19)
    eb = np.linspace(0, 1, 10)
    count = np.histogram2d(az, np.sin(np.deg2rad(el)), bins=(ab, eb))[0]
    visible = np.histogram2d(ex[:, 0], np.sin(np.deg2rad(ex[:, 1])), bins=(ab, eb))[0]
    ratio = np.divide(count, visible, out=np.zeros_like(count), where=visible > 0)
    ratio /= ratio.max()
    fig, axs = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)
    for ax, z, title in zip(
        axs,
        [count, visible, ratio],
        [
            "Heard track midpoints",
            "Visible catalogue, scan midpoints",
            "Heard / visible, peak normalized",
        ],
        strict=True,
    ):
        im = ax.pcolormesh(ab, np.rad2deg(np.arcsin(eb)), z.T, cmap="viridis", shading="auto")
        fig.colorbar(im, ax=ax)
        ax.set(xlabel="Azimuth (° clockwise from north)", ylabel="Elevation (°)", title=title)
    fig.suptitle(
        "Equal-solid-angle bins · visibility normalization is not a calibrated "
        "detection probability"
    )
    fig.savefig(output / "02-sky-density-exposure.png", dpi=160)
    plt.close(fig)
    fig, axs = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    for rate, c in colours.items():
        rr = [r for r in rows if r["rate"] == rate]
        axs[0, 0].hist(
            [r["az"][6] for r in rr],
            bins=np.arange(0, 361, 30),
            histtype="step",
            color=c,
            label=f"{rate:g} MS/s",
        )
        axs[0, 1].hist([r["el"][6] for r in rr], bins=np.arange(0, 91, 5), histtype="step", color=c)
    axs[0, 0].set(xlabel="Azimuth (°)", ylabel="Tracks")
    axs[0, 0].legend()
    axs[0, 1].set(xlabel="Elevation (°)", ylabel="Tracks")
    for ch in range(1, 5):
        rr = [r for r in rows if r["channel"] == ch]
        axs[1, 0].scatter(
            [r["az"][6] for r in rr], [r["el"][6] for r in rr], s=10, alpha=0.4, label=f"CH{ch}"
        )
    axs[1, 0].set(xlabel="Azimuth (°)", ylabel="Elevation (°)")
    axs[1, 0].legend()
    for edge in ["lower", "upper"]:
        rr = [r for r in rows if r["edge"] == edge]
        axs[1, 1].scatter(
            [r["az"][6] for r in rr], [r["el"][6] for r in rr], s=10, alpha=0.4, label=edge
        )
    axs[1, 1].set(xlabel="Azimuth (°)", ylabel="Elevation (°)")
    axs[1, 1].legend()
    fig.savefig(output / "03-sky-rate-channel-edge.png", dpi=160)
    plt.close(fig)
    unit = np.column_stack(
        [
            np.cos(np.deg2rad(el)) * np.sin(np.deg2rad(az)),
            np.cos(np.deg2rad(el)) * np.cos(np.deg2rad(az)),
            np.sin(np.deg2rad(el)),
        ]
    )
    centre = unit.mean(axis=0)
    centre /= np.linalg.norm(centre)
    distance = np.rad2deg(np.arccos(np.clip(unit @ centre, -1, 1)))
    summary = dict(
        input_reviews=len(reviews),
        quality_tracks=len(rows),
        scans=len(seen),
        unique_candidates=len({r["norad"] for r in rows}),
        quality_rule=(
            "fit and evaluation RMS <250 Hz and evaluation runner/top ratio >2; "
            "midpoint above horizon"
        ),
        elevation_q05_q50_q95=np.quantile(el, [0.05, 0.5, 0.95]).tolist(),
        mean_direction_azimuth_deg=float(np.rad2deg(np.arctan2(centre[0], centre[1])) % 360),
        mean_direction_elevation_deg=float(np.rad2deg(np.arcsin(centre[2]))),
        angular_radius_q50_q90_q95=np.quantile(distance, [0.5, 0.9, 0.95]).tolist(),
        per_rate={
            str(rate): dict(
                tracks=sum(r["rate"] == rate for r in rows),
                median_elevation_deg=float(
                    np.median([r["el"][6] for r in rows if r["rate"] == rate])
                ),
            )
            for rate in colours
        },
        site_conditioned=True,
        independent_location_evidence=False,
    )
    fig, axs = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)
    z = 90 - el
    east = z * np.sin(np.deg2rad(az))
    north = z * np.cos(np.deg2rad(az))
    density = axs[0].hexbin(
        east, north, gridsize=30, mincnt=1, extent=(-35, 35, -35, 35), cmap="viridis"
    )
    fig.colorbar(density, ax=axs[0], label="Candidate track midpoints")
    axs[0].plot(0, 0, "r+", ms=12, label="Zenith")
    for radius in [10, 20, 30]:
        circle = np.linspace(0, 2 * np.pi, 181)
        axs[0].plot(radius * np.cos(circle), radius * np.sin(circle), "k:", alpha=0.2)
    axs[0].set(
        xlabel="East of zenith (angular degrees)",
        ylabel="North of zenith (angular degrees)",
        aspect="equal",
        title="Zoomed empirical footprint",
    )
    axs[0].legend()
    for rate, c in colours.items():
        d = np.sort(distance[np.array([r["rate"] == rate for r in rows])])
        axs[1].plot(d, np.arange(1, len(d) + 1) / len(d), color=c, label=f"{rate:g} MS/s")
    axs[1].axhline(0.9, color="gray", ls=":")
    axs[1].set(
        xlabel="Angular distance from pooled mean direction (°)",
        ylabel="Cumulative track fraction",
        title="Empirical angular containment",
        xlim=(0, 45),
    )
    axs[1].legend()
    axs[1].grid(alpha=0.2)
    fig.savefig(output / "04-zenith-footprint-containment.png", dpi=160)
    plt.close(fig)
    write_json(output / "sky-summary.json", summary)
    write_json(output / "sky-tracks.json", rows)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["evidence", "reviews", "output"]:
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    render(a.evidence, a.reviews, a.output)
