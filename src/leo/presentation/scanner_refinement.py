"""PNG comparisons with known imposed shifts and explicit failure denominators."""

from __future__ import annotations

import io
from threading import RLock

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.analysis.starlink.refinement_comparison import comparison_errors, comparison_metrics
from leo.contracts.scanner_refinement import PROFILES, ComparisonEvidenceV1

_LOCK = RLock()
_LABELS = ("512", "8192", "512 + local", "Local + joint")
_COLORS = ("#737b8a", "#9562bd", "#237bb4", "#df7721")


def _png(figure: Figure) -> bytes:
    stream = io.BytesIO()
    FigureCanvasAgg(figure).print_png(stream, metadata={"Software": "Leo scanner refinement v1"})
    return stream.getvalue()


def render_scanner_refinement(evidence: ComparisonEvidenceV1) -> dict[str, bytes]:
    metrics = comparison_metrics(evidence.rows)
    errors = comparison_errors(evidence.rows)
    with _LOCK:
        figure = Figure(figsize=(14, 5.2), dpi=140)
        axes = figure.subplots(1, 3)
        panels = (
            ("frequency", "cfo_rms_hz", "Frequency-shift RMS within alias (Hz)"),
            ("delay", "delay_rms_ns", "Delay-recovery RMS (ns)"),
            ("delay", "cfo_rms_hz", "Delay-induced CFO RMS within alias (Hz)"),
        )
        for ax, (case, key, title) in zip(axes, panels, strict=True):
            group = [
                next(m for m in metrics if m.profile == p and m.case == case) for p in PROFILES
            ]
            values = [getattr(m, key) for m in group]
            if all(value is not None for value in values):
                bars = ax.bar(range(4), values, color=_COLORS)
                ax.bar_label(bars, fmt="%.2f", fontsize=8, padding=3)
                ax.set_ylim(0, max(max(values) * 1.3, 0.01))
            else:
                ax.text(0.5, 0.5, "No common recovered cases", ha="center", transform=ax.transAxes)
            ax.set_title(title, fontsize=10)
            ax.set_xticks(range(4), _LABELS, rotation=20)
            counts = ", ".join(f"{m.recovered}/{len(evidence.scheduled_probe_ids)}" for m in group)
            ax.set_xlabel(f"Recovered: {counts}\nCommon cases: {group[0].common}", fontsize=8)
            ax.grid(axis="y", alpha=0.2)
            ax.set_axisbelow(True)
        aliases = sum(m.alias_changes for m in metrics)
        figure.suptitle(
            f"Local / joint refinement · {evidence.sample_rate_hz / 1e6:g} MS/s\n"
            f"{evidence.session_id}",
            fontsize=12,
        )
        figure.text(
            0.5,
            0.015,
            f"Known shifts on stored IQ; relative consistency, not absolute accuracy. "
            f"Alias switches across profiles/tests: {aliases}; inspect raw-error PNG. "
            f"Failed probes: {len(evidence.failures)}.",
            ha="center",
            fontsize=8,
        )
        figure.tight_layout(rect=(0, 0.055, 1, 0.89))
        overview = _png(figure)

        figure = Figure(figsize=(12, 9), dpi=140)
        axes = figure.subplots(3, 1)
        for ax, case, key, label in (
            (axes[0], "frequency", "raw_cfo_hz", "Raw CFO-shift error (Hz)"),
            (axes[1], "delay", "delay_ns", "Delay-recovery error (ns)"),
            (axes[2], "delay", "raw_cfo_hz", "Raw delay-induced CFO error (Hz)"),
        ):
            for p, color, name in zip(PROFILES, _COLORS, _LABELS, strict=True):
                selected = [
                    e for e in errors if e["case"] == case and e["profile"] == p and e["recovered"]
                ]
                ax.scatter(
                    [e["time_s"] for e in selected],
                    [e[key] for e in selected],
                    s=25,
                    facecolors="none",
                    edgecolors=color,
                    label=name,
                )
            ax.axhline(0, color="black", linewidth=0.6)
            ax.set_yscale("symlog", linthresh=1)
            ax.set_ylabel(label)
            ax.grid(alpha=0.2)
        axes[0].legend(ncol=4, fontsize=9)
        axes[-1].set_xlabel(
            "Independent probe device time in capture (s); targets and receivers are not joined"
        )
        figure.suptitle(
            f"Every recovered probe: raw errors, including aliases\n{evidence.session_id}",
            fontsize=12,
        )
        figure.text(
            0.5,
            0.015,
            "Symmetric log scales preserve large errors. "
            "Empty/failed detections remain in the evidence denominators. "
            "No trajectory fit is used as truth.",
            ha="center",
            fontsize=9,
        )
        figure.tight_layout(rect=(0, 0.04, 1, 0.92))
        return {"shift-recovery": overview, "probe-comparison": _png(figure)}
