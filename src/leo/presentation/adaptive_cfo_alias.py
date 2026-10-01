"""Optional alias-context figures from sealed candidates, without new detections."""

from __future__ import annotations

import numpy as np
from matplotlib import rc_context
from matplotlib.figure import Figure

from leo.analysis.starlink import CFO_ALIAS_SPACING_HZ, fit_trajectory_bank
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.presentation.adaptive_hop_analysis import (
    _CFO_COLORS,
    _MARKERS,
    _axes_time,
    _save,
    adaptive_trajectory_configuration,
    project_adaptive_overview,
)
from leo.presentation.persistent_hop_analysis import _RENDER_LOCK

ALIAS_CONTEXT_HZ = 100_000.0


def alias_context_rows(rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return ±one-period copies inside the 100 kHz exterior bands only.

    Input columns are target, receiver, time, canonical CFO. Original arrays
    and scientific observation counts remain unchanged.
    """
    half = CFO_ALIAS_SPACING_HZ / 2
    copies = []
    for direction in (-1, 1):
        shifted = rows.copy()
        shifted[:, 3] += direction * CFO_ALIAS_SPACING_HZ
        frequency = shifted[:, 3]
        keep = (np.abs(frequency) >= half) & (np.abs(frequency) <= half + ALIAS_CONTEXT_HZ)
        copies.append(shifted[keep])
    return copies[0], copies[1]


def render_adaptive_cfo_alias_context(binding, manifest, visits) -> dict[str, bytes]:
    """Render four channels and a CH4 zoom with the existing overview associations."""
    data = project_adaptive_overview(binding, manifest, visits)
    config = adaptive_trajectory_configuration(binding.configuration.glrt64_margin_gate)
    banks = {key: fit_trajectory_bank(rows, config) for key, rows in data.observations.items()}
    metrics_sha = sha256_digest(canonical_json_bytes(manifest.model_dump(mode="json")))
    half = CFO_ALIAS_SPACING_HZ / 2
    figures = {}
    with _RENDER_LOCK, rc_context({"font.size": 11, "legend.fontsize": 9}):
        for name, channels, window in (
            ("cfo-alias-context", range(4), None),
            ("ch4-wrap-zoom", (3,), (180, 230)),
        ):
            figure = Figure(figsize=(15.5, 13 if window is None else 6.5), dpi=160)
            axes = figure.subplots(len(channels), 1, sharex=True, squeeze=False)[:, 0]
            for channel, axis in zip(channels, axes, strict=True):
                for sign in (-1, 1):
                    band = sorted((sign * half / 1000, sign * (half + ALIAS_CONTEXT_HZ) / 1000))
                    axis.axhspan(*band, color="#edf1f6", zorder=0)
                    axis.axhline(sign * half / 1000, color="#555555", linestyle=":", linewidth=1)
                    axis.text(
                        0.99,
                        sign * (half + 85_000) / 1000,
                        f"{sign:+d} alias copy",
                        transform=axis.get_yaxis_transform(),
                        ha="right",
                        va="center",
                        color="#596579",
                        fontsize=9,
                    )
                for edge in (0, 1):
                    target = channel + edge * 4
                    for rx in binding.configuration.receiver_ids:
                        rows = data.passed[
                            (data.passed[:, 0] == target) & (data.passed[:, 1] == rx)
                        ]
                        if not len(rows):
                            continue
                        style = dict(
                            s=12,
                            marker=_MARKERS[rx],
                            color=_CFO_COLORS[edge][rx],
                            linewidths=0.8,
                            rasterized=True,
                        )
                        axis.scatter(
                            rows[:, 2],
                            rows[:, 3] / 1000,
                            alpha=0.7,
                            label=f"{'LU'[edge]} RX{rx}",
                            **style,
                        )
                        for copy in alias_context_rows(rows):
                            axis.scatter(copy[:, 2], copy[:, 3] / 1000, alpha=0.45, **style)
                        bank = banks.get((target, rx))
                        if bank:
                            for track in bank.trajectories:
                                times = np.linspace(track.start_s, track.end_s, 80)
                                for shift in (-1, 0, 1):
                                    frequency = (
                                        track.frequency_hz(times) + shift * CFO_ALIAS_SPACING_HZ
                                    )
                                    axis.plot(
                                        times,
                                        frequency / 1000,
                                        color=_CFO_COLORS[edge][rx],
                                        linestyle="--",
                                        linewidth=1,
                                        alpha=0.6,
                                    )
                _axes_time(axis, binding)
                if window:
                    axis.set_xlim(*window)
                axis.set_ylim(-(half + ALIAS_CONTEXT_HZ) / 1000, (half + ALIAS_CONTEXT_HZ) / 1000)
                axis.set_yticks((-200, -100, 0, 100, 200))
                axis.set_ylabel(f"CH{channel + 1}\nPilot-relative CFO (kHz)")
                axis.set_xlabel("")
                if axis.get_legend_handles_labels()[0]:
                    axis.legend(loc="center right", ncol=2)
            axes[-1].set_xlabel("Device time since capture start (s); fractional candidate epochs")
            figure.suptitle(
                "CFO candidate associations with alias context\n"
                f"{binding.session_id} · period {CFO_ALIAS_SPACING_HZ / 1000:.3f} kHz\n"
                "Shaded bands: 100 kHz of shifted copies beyond each canonical boundary; "
                "not new detections",
                fontsize=13,
                y=0.985,
            )
            figure.text(
                0.5,
                0.018,
                "Dashed: overview associations, not downstream track IDs or satellite identities. "
                "Receivers and channel edges remain separate.",
                ha="center",
                fontsize=10,
            )
            figure.subplots_adjust(
                top=0.89 if window is None else 0.80,
                bottom=0.075 if window is None else 0.14,
                left=0.075,
                right=0.985,
                hspace=0.10,
            )
            figures[name] = _save(figure, binding, metrics_sha, None)
    return figures
