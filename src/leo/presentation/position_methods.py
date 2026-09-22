"""Plots for additional conditional position estimators, including abstentions."""

from io import BytesIO

import numpy as np
from matplotlib.figure import Figure

TITLES = {
    "expanded-doppler": "Expanded pass-balanced Doppler",
    "orbit-corrected": "Position with constrained orbital corrections",
    "identity-mixture": "Soft satellite association (experimental)",
}


def render_position_method(result, *, session_id, reference_position=None):
    """Reference coordinates enter only presentation, after inference is sealed."""
    figure = Figure(figsize=(13, 9), layout="constrained")
    axes = figure.subplots(2, 2)
    figure.suptitle(f"{session_id}\n{TITLES[result.method]} · conditional estimate, not a GPS fix")
    diagnostic = result.diagnostics
    summary = axes[0, 0]
    summary.axis("off")
    lines = [f"State: {result.state}"]
    if result.latitude_deg is not None:
        lines += [
            f"Latitude: {result.latitude_deg:.8f}°",
            f"Longitude: {result.longitude_deg:.8f}°",
        ]
        if result.horizontal_error_m is not None:
            lines.append(
                f"Horizontal error vs supplied reference: {result.horizontal_error_m:,.1f} m"
            )
    else:
        lines.append("No qualified position estimate")
    for key, label in (
        ("track_count", "Tracks"),
        ("source_count", "Candidate sources"),
        ("training_point_count", "Fit observations"),
        ("evaluation_point_count", "Evaluation observations"),
        ("training_rms_hz", "Fit RMS (Hz)"),
        ("evaluation_rms_hz", "Evaluation RMS (Hz)"),
    ):
        value = diagnostic.get(key)
        if value is not None:
            lines.append(
                f"{label}: {value:.2f}" if isinstance(value, float) else f"{label}: {value}"
            )
    lines += ["Reference used only after fitting.", "Uncertainty is not calibrated."]
    lines.extend(str(reason).replace("-", " ") for reason in result.reasons)
    summary.text(0, 1, "\n".join(lines), va="top", fontsize=10, wrap=True)
    location = axes[0, 1]
    if result.latitude_deg is not None:
        location.scatter(
            [result.longitude_deg],
            [result.latitude_deg],
            marker="x",
            s=85,
            label="Conditional estimate",
        )
        if reference_position is not None:
            location.scatter(
                [reference_position.longitude_deg],
                [reference_position.latitude_deg],
                marker="+",
                s=90,
                label="Supplied reference (evaluation only)",
            )
            center_latitude = (result.latitude_deg + reference_position.latitude_deg) / 2
            center_longitude = (result.longitude_deg + reference_position.longitude_deg) / 2
            cosine = max(0.05, float(np.cos(np.deg2rad(center_latitude))))
            half_span = (
                max(
                    abs(result.latitude_deg - reference_position.latitude_deg),
                    abs(result.longitude_deg - reference_position.longitude_deg) * cosine,
                    0.002,
                )
                * 0.65
            )
            location.set_xlim(
                center_longitude - half_span / cosine, center_longitude + half_span / cosine
            )
            location.set_ylim(center_latitude - half_span, center_latitude + half_span)
            location.set_aspect(1 / cosine)
        location.set_xlabel("Longitude (degrees)")
        location.set_ylabel("Latitude (degrees)")
        location.ticklabel_format(useOffset=False)
        location.legend(fontsize=8)
        location.grid(alpha=0.2)
    else:
        location.axis("off")
        location.text(0.5, 0.5, "Position unavailable\nSee status and reasons", ha="center")
    residual = axes[1, 0]
    plotted = False
    for key, label in (("training_residual_hz", "Fit"), ("evaluation_residual_hz", "Evaluation")):
        values = np.asarray(diagnostic.get(key, []), dtype=float)
        if values.size:
            residual.plot(np.arange(len(values)), values, ".", ms=2, alpha=0.6, label=label)
            plotted = True
    if plotted:
        residual.set(
            xlabel="Observation index (separate partitions)", ylabel="Doppler residual (Hz)"
        )
        residual.legend()
        residual.grid(alpha=0.2)
    else:
        residual.axis("off")
        residual.text(0.5, 0.5, "Residual series unavailable", ha="center")
    detail = axes[1, 1]
    modes = diagnostic.get("modes", {})
    weights = (
        modes.get("candidate_posterior", [])
        if isinstance(modes, dict) and result.method == "identity-mixture"
        else []
    )
    corrections = diagnostic.get("diagnostics", {}).get("rate_corrections_s_h", {})
    if weights:
        width = max(len(row) for row in weights)
        matrix = np.full((len(weights), width + 1), np.nan)
        unassigned = modes.get("unassigned_posterior", [])
        for i, row in enumerate(weights):
            matrix[i, : len(row)] = row
            if i < len(unassigned):
                matrix[i, -1] = unassigned[i]
        heatmap = detail.imshow(matrix, aspect="auto", vmin=0, vmax=1, cmap="viridis")
        detail.set_xticks(range(width + 1), [str(i + 1) for i in range(width)] + ["Unassigned"])
        detail.set(
            xlabel="Candidate review rank (NORAD varies by track)",
            ylabel="Track index",
            title="Model weights · shortlist conditional, uncalibrated",
        )
        figure.colorbar(heatmap, ax=detail, label="Fitting weight")
    elif corrections:
        keys = sorted(corrections)
        detail.plot(range(len(keys)), [corrections[key] for key in keys], ".")
        detail.axhline(0, color="grey", lw=0.7)
        detail.set(
            xlabel="Satellite index (NORAD mapping in JSON)",
            ylabel="Orbital phase-rate correction (s/hour)",
            title="Shared satellite corrections",
        )
        detail.grid(alpha=0.2)
    else:
        detail.axis("off")
    notes = [
        "Measurement and identity provenance: accompanying JSON",
        "Fit and evaluation membership is frozen before positioning.",
        "Catalogue identities were screened using a known site.",
        "This is not a blind location solution.",
    ]
    for key in (
        "cohort_session_count",
        "window_hours",
        "exact_orbit_max_error_hz",
        "candidate_support_certified",
        "effective_information_warning",
    ):
        if key in diagnostic:
            notes.append(f"{key.replace('_', ' ')}: {diagnostic[key]}")
    if not weights and not corrections:
        detail.text(0, 1, "\n\n".join(notes), va="top", fontsize=10, wrap=True)
    output = BytesIO()
    figure.savefig(output, format="png", dpi=120)
    return output.getvalue()
