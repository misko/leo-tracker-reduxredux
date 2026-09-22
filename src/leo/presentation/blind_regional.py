"""Render independent regional association evidence from its sealed document."""

from io import BytesIO

import numpy as np
from matplotlib.figure import Figure

from leo.contracts.blind_regional import BlindRegionalDocumentV1


def render_blind_regional(document: BlindRegionalDocumentV1) -> dict[str, bytes]:
    """Reference is evaluation-only; no plot affects association or fitting."""
    images = {}
    for name in ("blind-association", "blind-position", "blind-position-modes"):
        figure = Figure(figsize=(13, 9), layout="constrained")
        figure.suptitle(
            f"{document.session_id} · Denver-region blind association\n"
            "Known site excluded from inference · diagnostic, not a position fix"
        )
        if document.state != "diagnostic":
            ax = figure.subplots()
            ax.axis("off")
            ax.text(0.05, 0.8, f"{document.state}\n" + "\n".join(document.reasons), wrap=True)
        elif name == "blind-association":
            _associations(figure, document)
        elif name == "blind-position":
            _region(figure, document)
        else:
            _modes(figure, document)
        output = BytesIO()
        figure.savefig(output, format="png", dpi=130)
        images[name] = output.getvalue()
    return images


def _associations(figure, document):
    tracks = document.tracks[:12]
    axes = figure.subplots(4, 3, squeeze=False).ravel()
    for ax, track in zip(axes, tracks, strict=False):
        data = track.diagnostics
        times = np.asarray(data.get("time_s", []), dtype=float)
        observed = np.asarray(data.get("measured_hz", []), dtype=float)
        predicted = np.asarray(data.get("prediction_hz", []), dtype=float)
        if times.size and observed.size == times.size:
            origin = observed[0]
            ax.plot(times, (observed - origin) / 1000, ".", ms=3, label="Measured")
            if predicted.size == times.size:
                ax.plot(times, (predicted - origin) / 1000, lw=1, label="Train-fitted candidate")
            ax.set(xlabel="Track time (s)", ylabel="Relative CFO (kHz)")
        else:
            ax.bar(
                [str(c.catalog_number) for c in track.candidates] + ["Null"],
                [c.soft_weight for c in track.candidates] + [track.unassigned_weight],
            )
            ax.set_ylabel("Composite association weight")
        leader = track.candidates[0] if track.candidates else None
        ax.set_title(
            f"{track.track_id[-10:]} · {track.state}\n"
            + (
                f"NORAD {leader.catalog_number} · weight {leader.soft_weight:.2f}"
                if leader
                else "Unassigned"
            ),
            fontsize=9,
        )
        ax.grid(alpha=0.2)
    for ax in axes[len(tracks) :]:
        ax.axis("off")
    figure.supxlabel(
        f"Displaying {len(tracks)} / {len(document.tracks)} tracks; all results in JSON. "
        "Candidate weights are not calibrated probabilities."
    )


def _region(figure, document):
    ax, summary = figure.subplots(1, 2)
    data = document.diagnostics
    east = np.asarray(data.get("map_east_km", []), dtype=float)
    north = np.asarray(data.get("map_north_km", []), dtype=float)
    score = np.asarray(data.get("map_training_log_evidence", []), dtype=float)
    if east.size and east.size == north.size == score.size:
        points = ax.scatter(east, north, c=score, s=15)
        figure.colorbar(points, ax=ax, label="Training composite evidence (coarse subset)")
    ax.set(xlabel="East of Denver centre (km)", ylabel="North of Denver centre (km)")
    ax.set_xlim(-document.region.width_km / 2, document.region.width_km / 2)
    ax.set_ylim(-document.region.height_km / 2, document.region.height_km / 2)
    ax.grid(alpha=0.2)
    summary.axis("off")
    lines = [
        "Entire causal eligible Starlink catalogue considered",
        "at trial receiver positions; no Sausalito shortlist.",
        f"Selected tracks: {document.accounting.track_count}",
        f"Selected observations: {document.accounting.eligible_observation_count}",
        f"Region: {document.region.width_km:,.0f} × {document.region.height_km:,.0f} km",
        "Fixed altitude: 0 m; nominal causal orbits.",
        "Constant frequency offset fitted per track.",
        "No calibrated geographic uncertainty.",
    ]
    if document.position_modes:
        mode = document.position_modes[0]
        lines += [
            "",
            f"Training leader: {mode.latitude_deg:.6f}°, {mode.longitude_deg:.6f}°",
            f"Held-out composite score: {mode.heldout_score:.2f}",
        ]
    lines.extend(document.reasons)
    summary.text(0, 1, "\n".join(lines), va="top", wrap=True, fontsize=10)


def _modes(figure, document):
    ax, scores = figure.subplots(1, 2)
    modes = [mode for mode in document.position_modes if mode.latitude_deg is not None]
    for mode in modes:
        ax.scatter(mode.longitude_deg, mode.latitude_deg, marker="x", s=70)
        ax.annotate(str(mode.rank), (mode.longitude_deg, mode.latitude_deg))
    if document.evaluation is not None:
        reference = document.evaluation.reference
        ax.scatter(
            reference.longitude_deg,
            reference.latitude_deg,
            marker="+",
            c="red",
            s=100,
            label="Reference revealed after fitting",
        )
        ax.legend(fontsize=8)
    ax.set(xlabel="Longitude (degrees)", ylabel="Latitude (degrees)")
    ax.grid(alpha=0.2)
    ranks = [mode.rank for mode in modes]
    scores.plot(ranks, [mode.training_score for mode in modes], "o-", label="Training")
    scores.plot(ranks, [mode.heldout_score for mode in modes], "o-", label="Held-out predictive")
    scores.set(xlabel="Position mode ranked by training evidence", ylabel="Composite evidence")
    scores.legend()
    scores.grid(alpha=0.2)
    figure.supxlabel(
        "Alternative modes are retained; no uniqueness or calibrated position fix is claimed."
    )
