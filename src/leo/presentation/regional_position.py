"""Sacramento search maps; reference coordinates enter only this presentation stage."""

import math
from io import BytesIO
from textwrap import fill

from matplotlib.figure import Figure
from matplotlib.patches import Circle

from leo.contracts.regional_position_products import RegionalPositionDocumentV1
from leo.contracts.regional_position_v2 import RegionalPositionDocumentV2


def regional_position_figure(
    document: RegionalPositionDocumentV1 | RegionalPositionDocumentV2, method: str
) -> Figure:
    result = next((item for item in document.methods if item.name == method), None)
    if result is None:
        raise ValueError("unknown regional positioning method")
    figure = Figure(figsize=(9, 8), layout="constrained")
    axis = figure.subplots()
    label = "Hard60 / V16" if document.schema_version == 2 else method
    figure.suptitle(f"{document.session_id} · {label} · diagnostic, not a position fix")
    axis.add_patch(Circle((0, 0), document.prior_radius_km, fill=False, color="gray", alpha=0.4))
    points = [point for point in result.points if point.objective is not None]
    if points:
        plotted = axis.scatter(
            [p.east_km for p in points],
            [p.north_km for p in points],
            c=[p.objective for p in points if p.objective is not None],
            s=12,
            cmap="viridis_r",
        )
        figure.colorbar(
            plotted, ax=axis, label="Coarse fitted-c negative log likelihood (lower is better)"
        )
    failed = [point for point in result.points if point.objective is None]
    if failed:
        axis.scatter(
            [p.east_km for p in failed],
            [p.north_km for p in failed],
            marker="x",
            c="gray",
            s=10,
            label="Unscored trial",
        )
    descriptions = []
    for arm, marker, color in zip(result.arms, ("D", "s"), ("red", "blue"), strict=True):
        selected = arm.selected
        if selected is None:
            descriptions.append(f"{arm.name}: unavailable ({'; '.join(arm.reasons)})")
            continue
        axis.plot(
            selected.east_km,
            selected.north_km,
            marker=marker,
            color=color,
            linestyle="none",
            label=f"{arm.name} selected estimate",
            markersize=7,
        )
        rms = (
            "unavailable"
            if selected.posterior_rms_hz is None
            else f"{selected.posterior_rms_hz:.1f} Hz"
        )
        convergence = "stationary" if selected.converged else "not converged"
        boundary = "; boundary" if selected.boundary else ""
        descriptions.append(
            f"{arm.name}: reference error {selected.horizontal_error_m / 1000:.2f} km; "
            f"residual RMS {rms}; {convergence}{boundary}"
        )
    lat0, lon0 = map(math.radians, (document.prior_latitude_deg, document.prior_longitude_deg))
    lat, lon = map(
        math.radians, (document.reference_latitude_deg, document.reference_longitude_deg)
    )
    angular = math.acos(
        max(
            -1,
            min(
                1,
                math.sin(lat0) * math.sin(lat)
                + math.cos(lat0) * math.cos(lat) * math.cos(lon - lon0),
            ),
        )
    )
    bearing = math.atan2(
        math.sin(lon - lon0) * math.cos(lat),
        math.cos(lat0) * math.sin(lat) - math.sin(lat0) * math.cos(lat) * math.cos(lon - lon0),
    )
    axis.plot(
        6371.0088 * angular * math.sin(bearing),
        6371.0088 * angular * math.cos(bearing),
        "k+",
        markersize=10,
        label="Reference (evaluation only)",
    )
    axis.set(
        title=f"Sacramento {document.prior_radius_km:g} km prior · {document.windows} windows\n"
        + "\n".join(fill(description, width=90) for description in descriptions),
        xlabel="East of prior centre (km)",
        ylabel="North of prior centre (km)",
        xlim=(-document.prior_radius_km, document.prior_radius_km),
        ylim=(-document.prior_radius_km, document.prior_radius_km),
    )
    axis.set_aspect("equal")
    axis.grid(alpha=0.2)
    axis.legend(fontsize=8)
    figure.supxlabel(
        f"Search: {result.search_stop_reason}; {result.deferred_cells} deferred cells.\n"
        "Final RF ablation shares fitted-c calibration and association. "
        "Scores are in-sample; no global optimum certified.",
        fontsize=8,
    )
    return figure


def render_regional_position(
    document: RegionalPositionDocumentV1 | RegionalPositionDocumentV2, method: str
) -> bytes:
    figure = regional_position_figure(document, method)
    stream = BytesIO()
    figure.savefig(stream, format="png", dpi=120)
    return stream.getvalue()
