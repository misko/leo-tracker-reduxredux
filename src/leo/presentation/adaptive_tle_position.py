"""Presentation for blind bounded best-first TLE position selection."""

from io import BytesIO

import numpy as np
from matplotlib.figure import Figure


def render_adaptive_tle_position(document) -> bytes:
    figure = Figure(figsize=(13, 6), layout="constrained")
    axes = figure.subplots(1, 2)
    figure.suptitle(
        f"{document.session_id} · blind adaptive TLE position selection · not a position fix"
    )
    if document.state != "diagnostic":
        for axis in axes:
            axis.axis("off")
        axes[0].text(
            0,
            1,
            "\n".join(
                (
                    f"State: {document.state}",
                    "No qualified position selection was published.",
                    *document.reasons,
                    "Known position was not used for inference.",
                )
            ),
            va="top",
            wrap=True,
        )
    else:
        points = document.diagnostics.get("evaluated_points", {})
        for axis, prior in zip(axes, document.priors, strict=True):
            rows = points.get(prior.name, []) if isinstance(points, dict) else []
            if rows:
                east = np.asarray([row["east_km"] for row in rows], dtype=float)
                north = np.asarray([row["north_km"] for row in rows], dtype=float)
                score = np.asarray([row["capped_weighted_rmse_hz"] for row in rows], dtype=float)
                plotted = axis.scatter(east, north, c=score, s=9, cmap="viridis_r")
                figure.colorbar(plotted, ax=axis, label="Selection score: capped RMSE (Hz)")
            axis.plot(
                prior.selected.east_km,
                prior.selected.north_km,
                "rD",
                markersize=7,
                label="Selected global incumbent",
            )
            axis.plot(
                prior.finest.east_km,
                prior.finest.north_km,
                "k*",
                markersize=9,
                label="Best evaluated 12.5 km centre",
            )
            reference = document.diagnostics.get("reference_evaluation_only", {})
            if isinstance(reference, dict) and reference:
                # Reference is transformed only for presentation after inference.
                lat0, lon0 = np.deg2rad(
                    [prior.region.center_latitude_deg, prior.region.center_longitude_deg]
                )
                lat, lon = np.deg2rad([reference["latitude_deg"], reference["longitude_deg"]])
                angular = np.arccos(
                    np.clip(
                        np.sin(lat0) * np.sin(lat)
                        + np.cos(lat0) * np.cos(lat) * np.cos(lon - lon0),
                        -1,
                        1,
                    )
                )
                bearing = np.arctan2(
                    np.sin(lon - lon0) * np.cos(lat),
                    np.cos(lat0) * np.sin(lat) - np.sin(lat0) * np.cos(lat) * np.cos(lon - lon0),
                )
                axis.plot(
                    6371.0088 * angular * np.sin(bearing),
                    6371.0088 * angular * np.cos(bearing),
                    "k+",
                    markersize=9,
                    label="Reference (evaluation only)",
                )
            axis.set(
                title=(
                    f"{prior.name.title()} 500 km prior\n"
                    f"selected {prior.selected.capped_weighted_rmse_hz:.2f} Hz · "
                    f"{prior.accounting.eligible_track_count} tracks · "
                    f"{prior.accounting.eligible_observation_count} observations"
                ),
                xlabel="East of prior centre (km)",
                ylabel="North of prior centre (km)",
                xlim=(-500, 500),
                ylim=(-500, 500),
            )
            axis.set_aspect("equal")
            axis.grid(alpha=0.2)
            axis.legend(fontsize=8)
        figure.text(
            0.5,
            0.005,
            "Identity is selected by frozen randomized-evaluation RMS; the score is selection "
            "evidence, not independent final-test accuracy or a calibrated position fix.",
            ha="center",
            fontsize=8,
        )
    stream = BytesIO()
    figure.savefig(stream, format="png", dpi=120)
    return stream.getvalue()
