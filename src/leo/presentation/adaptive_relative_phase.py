"""PNG evidence for every scan, including unsupported or empty scans."""

from io import BytesIO

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure


def _png(figure):
    stream = BytesIO()
    FigureCanvasAgg(figure).print_png(stream)
    return stream.getvalue()


def render_relative_phase(visits, *, session_id, total_visits, applicable=True):
    figure = Figure(figsize=(12, 9), layout="constrained")
    axes = figure.subplots(3, 1)
    indexes = [v.visit_index for v in visits]
    for key, label in [
        ("tracked_coherence", "A-tracked B coherence"),
        ("wrong_time_coherence", "Wrong-time control"),
    ]:
        axes[0].plot(indexes, [v.evidence.get(key, np.nan) for v in visits], ".-", label=label)
    axes[1].plot(
        indexes,
        [v.evidence.get("band_phase_rms_deg", np.nan) for v in visits],
        ".",
        label="B − A block RMS",
    )
    for visit in visits:
        if visit.evidence.get("pilot_held_rms_deg") is not None:
            axes[1].plot(
                visit.visit_index, visit.evidence["pilot_held_rms_deg"], "x", color="tab:orange"
            )
    axes[1].plot(
        [],
        [],
        "x",
        color="tab:orange",
        label="Pilot − broadband frame-matched RMS (different support)",
    )
    counts = [
        sum(v.state == "supported" for v in visits),
        sum(v.state != "supported" for v in visits),
    ]
    axes[2].bar(["Broadband supported", "Insufficient signal"], counts)
    axes[0].set_ylabel("Coherence")
    axes[1].set_ylabel("Discrepancy (degrees)")
    axes[2].set_ylabel("Selected dwell count")
    for ax in axes[:2]:
        ax.set_xlabel("Visit index")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.2)
    status = (
        "No qualifying paired dwells"
        if applicable
        else "Not applicable: requires simultaneous RX0/RX1"
    )
    if not visits:
        axes[0].text(0.5, 0.5, status, transform=axes[0].transAxes, ha="center")
    figure.suptitle(
        f"{session_id} · within-dwell receiver-relative phase\n"
        f"{len(visits)} phase-blind selected dwells / {total_visits} total"
        " · maximum 64 · no geometric-phase claim"
    )
    output = {"relative-phase-overview": _png(figure)}
    # At most 12 representative dwells per overview page; numerical checkpoints retain all 64.
    chosen = sorted(visits, key=lambda v: (v.state != "supported", v.visit_index))[:12]
    figure = Figure(figsize=(14, 12), layout="constrained")
    axes = figure.subplots(4, 3)
    for ax in axes.flat:
        ax.set_visible(False)
    for ax, visit in zip(axes.flat, chosen, strict=False):
        ax.set_visible(True)
        e = visit.evidence
        ax.plot(
            np.array(e.get("scalar_time_s", [])) * 1000,
            np.degrees(e.get("scalar_phase_rad", [])),
            ".",
            ms=2,
            color="gray",
            label="Common-band phase",
        )
        offset = e.get("training_offset_rad")
        if offset is not None:
            rows = e.get("pilot_rows", [])
            ax.plot(
                [r["time_s"] * 1000 for r in rows],
                np.degrees(
                    np.angle(np.exp(1j * np.array([r["pilot_phase_rad"] - offset for r in rows])))
                ),
                "o",
                ms=4,
                label="Pilot, training offset",
            )
            ax.plot(
                [r["time_s"] * 1000 for r in rows],
                np.degrees([r["broadband_phase_rad"] for r in rows]),
                "x",
                ms=5,
                label="Broadband, frame-matched",
            )
        rms = e.get("pilot_held_rms_deg")
        label = "Pilot check unavailable" if rms is None else f"Pilot RMS {rms:.1f}°"
        ax.set_title(f"Visit {visit.visit_index} · {visit.state}\n{label}", fontsize=9)
        ax.axvline(60, c="gray", ls="--")
        ax.set_ylim(-185, 185)
        ax.set_xlabel("Dwell time (ms)")
        ax.set_ylabel("Residual phase (°)")
        ax.grid(alpha=0.2)
    if chosen:
        axes.flat[0].legend(fontsize=6)
    else:
        axes.flat[0].set_visible(True)
        axes.flat[0].text(
            0.5, 0.5, status, transform=axes.flat[0].transAxes, ha="center", wrap=True
        )
    figure.suptitle(
        f"{session_id} · representative phase trajectories\n"
        "Separate reference per retune · dashed line: training / later check"
        " · all selected results retained numerically"
    )
    output["relative-phase-dwells"] = _png(figure)
    return output
