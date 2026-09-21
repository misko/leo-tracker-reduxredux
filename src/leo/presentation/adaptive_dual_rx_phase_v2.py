"""Render retained adaptive double-difference hypotheses without joining gaps."""

from __future__ import annotations

from io import BytesIO

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.scanner.adaptive_dual_rx_phase_product_v2 import AdaptiveDualRxPhaseVisitV2  # noqa: E402


def render_adaptive_dual_rx_phase_v2(visits: tuple[AdaptiveDualRxPhaseVisitV2, ...]) -> bytes:
    rows = [(visit, item) for visit in visits for item in visit.hypotheses]
    if not rows:
        raise ValueError("no double-difference hypothesis is available to render")
    time_s = np.asarray([item.common_session_time_s for _, item in rows])
    phase_deg = np.degrees([item.wrapped_high_minus_low_rad for _, item in rows])
    sigma_deg = np.degrees([item.standard_error_rad for _, item in rows])
    separation_khz = np.asarray([item.alias_aware_signal_separation_hz for _, item in rows]) / 1e3
    async_ms = np.asarray([item.asynchronous_center_separation_s for _, item in rows]) * 1e3
    target = np.asarray([visit.target_index for visit, _ in rows])
    lower_only = all(visit.edge == "lower" for visit, _ in rows)
    upper_only = all(visit.edge == "upper" for visit, _ in rows)
    color_min, color_max = (0, 3) if lower_only else (4, 7) if upper_only else (0, 7)
    figure, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True, layout="constrained")
    scatter = axes[0].scatter(
        time_s, phase_deg, c=target, cmap="tab10", vmin=color_min, vmax=color_max, alpha=0.8
    )
    axes[0].errorbar(time_s, phase_deg, yerr=sigma_deg, fmt="none", color="0.5", alpha=0.35)
    axes[0].set_ylabel("wrapped high−low phase (deg)")
    axes[0].set_ylim(-190, 190)
    axes[0].set_title("All phase-blind two-signal hypotheses; aliases are unresolved")
    figure.colorbar(
        scatter,
        ax=axes[0],
        label="target index",
        ticks=range(color_min, color_max + 1),
    )
    axes[1].scatter(time_s, separation_khz, c=target, cmap="tab10", vmin=color_min, vmax=color_max)
    axes[1].set_ylabel("alias-aware signal separation (kHz)")
    axes[2].scatter(time_s, async_ms, c=target, cmap="tab10", vmin=color_min, vmax=color_max)
    axes[2].set_ylabel("signal-center offset (ms)")
    axes[2].set_xlabel("seconds from capture origin")
    for axis in axes:
        axis.grid(alpha=0.2)
    figure.suptitle(
        "Adaptive dual-RX phase versus time — measured double difference; geometry unavailable"
    )
    stream = BytesIO()
    figure.savefig(stream, format="png", dpi=180)
    plt.close(figure)
    return stream.getvalue()
