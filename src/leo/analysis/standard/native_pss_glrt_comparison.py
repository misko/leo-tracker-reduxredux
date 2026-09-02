"""Paired native-25 PSS versus 2.5 MS/s GLRT frame-timing diagnostic."""

from __future__ import annotations

import io
import threading

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.contracts.standard_native_glrt_epoch import (
    NativeGlrtEpochLockletV1,
    NativeGlrtEpochObservationV1,
    StandardNativeGlrtEpochTrackingV1,
)
from leo.contracts.standard_native_pss import (
    NativePssSearchOriginV1,
    NativePssTimingTrackV1,
    StandardNativePssFrameTimingV1,
)

_RENDER_LOCK = threading.RLock()
_COLORS = ("#2563eb", "#7c3aed", "#0891b2", "#be123c")


def render_native25_pss_vs_2p5_glrt_png(
    pss_products: tuple[StandardNativePssFrameTimingV1, ...],
    glrt_epoch_products: tuple[StandardNativeGlrtEpochTrackingV1, ...],
) -> bytes:
    """Render same-dimension timing residuals and frequency-change agreement.

    PSS selection is blind-only.  GLRT is selected independently on each 2.5
    MS/s receiver path.  The sensors are joined only for this presentation and
    are never used to acquire or choose one another's observations.
    """

    session_ids = {
        *(item.source.session_id for item in pss_products),
        *(item.source.session_id for item in glrt_epoch_products),
    }
    if len(session_ids) > 1:
        raise ValueError("PSS/GLRT comparison crossed recording sessions")
    native_pss = tuple(item for item in pss_products if item.source.sample_rate_hz == 25_000_000)
    low_glrt = tuple(
        item for item in glrt_epoch_products if item.source.sample_rate_hz == 2_500_000
    )
    selected = _select_blind_pss_track(native_pss)

    with _RENDER_LOCK:
        figure = Figure(figsize=(16, 11), constrained_layout=True)
        FigureCanvasAgg(figure)
        axes = figure.subplots(3, 1, sharex=True)
        for axis in axes:
            axis.grid(True, alpha=0.22)
        session_id = next(iter(session_ids), "unknown-session")
        if selected is None:
            for axis in axes:
                axis.text(
                    0.5,
                    0.5,
                    "No independently associated native 25 MS/s PSS track",
                    ha="center",
                    va="center",
                    transform=axis.transAxes,
                )
            figure.suptitle(
                f"{session_id} · native 25 MS/s PSS versus dual 2.5 MS/s GLRT\n"
                "PSS: 125 ms complete windows / 62.5 ms stride · no clipped blocks"
            )
            return _save(figure)

        pss, track = selected
        modes_by_id = {item.mode_id: item for item in pss.modes}
        modes = tuple(modes_by_id[item] for item in track.mode_ids)
        pss_device_times = np.asarray([item.center_time_s for item in modes], dtype=float)
        pss_utc_times = pss.source.timing.first_estimate_utc_ns / 1e9 + pss_device_times
        pss_local = pss_device_times - track.time_origin_s
        coefficients = np.asarray(track.coefficients_descending_s, dtype=float)
        pss_phase = (
            np.polyval(coefficients, pss_local) + np.asarray(track.residuals_us, dtype=float) / 1e6
        )
        phase_reference = float(np.mean(pss_device_times))
        affine = np.polyfit(pss_device_times - phase_reference, pss_phase, 1)
        pss_linear_residual_us = (
            pss_phase - np.polyval(affine, pss_device_times - phase_reference)
        ) * 1e6
        pss_quadratic_residual_us = np.asarray(track.residuals_us, dtype=float)
        absolute_reference_s = float(np.mean(pss_utc_times))
        earliest_utc_s = min(
            pss.source.timing.first_estimate_utc_ns / 1e9,
            *(item.source.timing.first_estimate_utc_ns / 1e9 for item in low_glrt),
        )
        pss_plot_time = pss_utc_times - earliest_utc_s

        axes[0].scatter(
            pss_plot_time,
            pss_linear_residual_us,
            marker="x",
            s=24,
            color="#f97316",
            label=f"native-25 PSS · {pss.source.radio_id}/RX{pss.source.receiver_id}",
            zorder=4,
        )
        axes[1].scatter(
            pss_plot_time,
            pss_quadratic_residual_us,
            marker="x",
            s=24,
            color="#f97316",
            label="native-25 PSS",
            zorder=4,
        )

        overlapping_glrt: list[
            tuple[
                StandardNativeGlrtEpochTrackingV1,
                NativeGlrtEpochLockletV1,
                np.ndarray,
                tuple[NativeGlrtEpochObservationV1, ...],
            ]
        ] = []
        pss_start = float(pss_utc_times[0])
        pss_stop = float(pss_utc_times[-1])
        for product in low_glrt:
            source_utc_s = product.source.timing.first_estimate_utc_ns / 1e9
            for locklet in product.locklets:
                if locklet.linear_fit is None or locklet.quadratic_fit is None:
                    continue
                observations = tuple(item for item in locklet.observations if item.epoch_fit_inlier)
                utc_times = source_utc_s + np.asarray(
                    [item.global_center_time_s for item in observations], dtype=float
                )
                keep = (utc_times >= pss_start) & (utc_times <= pss_stop)
                if np.count_nonzero(keep) < 3:
                    continue
                retained = tuple(
                    item
                    for item, selected_item in zip(observations, keep, strict=True)
                    if selected_item
                )
                overlapping_glrt.append((product, locklet, utc_times[keep], retained))

        rf_reference_hz = (
            float(np.median([item.rf_reference_hz for item in low_glrt]))
            if low_glrt
            else 9_750_000_000.0 + pss.source.tuned_center_frequency_hz
        )
        pss_curvature = 2.0 * coefficients[0]
        pss_drift_at_reference = (
            2.0
            * coefficients[0]
            * (
                absolute_reference_s
                - pss.source.timing.first_estimate_utc_ns / 1e9
                - track.time_origin_s
            )
            + coefficients[1]
        )
        pss_drift = 2.0 * coefficients[0] * pss_local + coefficients[1]
        pss_frequency_change_hz = -rf_reference_hz * (pss_drift - pss_drift_at_reference)
        axes[2].plot(
            pss_plot_time,
            pss_frequency_change_hz / 1e3,
            color="#f97316",
            linewidth=2.2,
            label=(
                "native-25 PSS phase derivative · "
                f"rate {-rf_reference_hz * pss_curvature / 1e3:+.3f} kHz/s"
            ),
        )

        for index, (product, locklet, utc_times, observations) in enumerate(overlapping_glrt):
            color = _COLORS[index % len(_COLORS)]
            label = (
                f"2.5 GLRT · {product.source.radio_id}/RX{product.source.receiver_id} · "
                f"segment {locklet.continuity_segment_index}"
            )
            plot_time = utc_times - earliest_utc_s
            axes[0].scatter(
                plot_time,
                [_required_residual(item.linear_residual_s) * 1e6 for item in observations],
                s=8,
                alpha=0.55,
                color=color,
                label=label,
            )
            axes[1].scatter(
                plot_time,
                [_required_residual(item.quadratic_residual_s) * 1e6 for item in observations],
                s=8,
                alpha=0.55,
                color=color,
                label=label,
            )
            selection = locklet.cfo_selection
            if selection.quadratic_coefficients_hz is None or selection.reference_time_s is None:
                continue
            source_utc_s = product.source.timing.first_estimate_utc_ns / 1e9
            local_times = utc_times - source_utc_s - selection.reference_time_s
            reference_local = absolute_reference_s - source_utc_s - selection.reference_time_s
            c0, c1, c2 = selection.quadratic_coefficients_hz
            cfo = c0 + c1 * local_times + 0.5 * c2 * local_times**2
            reference_cfo = c0 + c1 * reference_local + 0.5 * c2 * reference_local**2
            axes[2].plot(
                plot_time,
                (cfo - reference_cfo) / 1e3,
                color=color,
                linestyle="--",
                linewidth=1.6,
                label=f"{label} canonical CFO",
            )

        if not overlapping_glrt:
            axes[0].text(
                0.5,
                0.08,
                "No complete 2.5 MS/s GLRT epoch locklet overlaps the selected PSS track",
                ha="center",
                transform=axes[0].transAxes,
            )
        for axis in axes:
            axis.axhline(0.0, color="#111827", linewidth=0.8)
            axis.legend(loc="best", fontsize=7)
        axes[0].set_ylabel("Linear-fit residual (µs)")
        axes[0].set_title("A · Same-dimension frame timing after independent affine fits")
        axes[1].set_ylabel("Quadratic-fit residual (µs)")
        axes[1].set_title("B · Independent quadratic timing residuals")
        axes[2].set_ylabel("Change from common reference (kHz)")
        axes[2].set_xlabel("Seconds from earliest stream first-sample estimate")
        axes[2].set_title("C · PSS phase-derived frequency change versus canonical GLRT CFO")
        figure.suptitle(
            f"{session_id} · native 25 MS/s PSS versus dual 2.5 MS/s GLRT\n"
            "PSS: 125 ms complete windows / 62.5 ms stride · independent acquisition · "
            "no clipped blocks"
        )
        return _save(figure)


def _select_blind_pss_track(
    products: tuple[StandardNativePssFrameTimingV1, ...],
) -> tuple[StandardNativePssFrameTimingV1, NativePssTimingTrackV1] | None:
    candidates = tuple(
        (product, track)
        for product in products
        for track in product.tracks
        if track.origin is NativePssSearchOriginV1.INDEPENDENT_BLIND
    )
    return max(
        candidates,
        key=lambda item: (
            len(item[1].mode_ids),
            item[1].time_stop_s - item[1].time_start_s,
            -item[1].rms_residual_us,
            item[1].track_id,
        ),
        default=None,
    )


def _save(figure: Figure) -> bytes:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=150, metadata={"Software": "leo-tracker"})
    figure.clear()
    return buffer.getvalue()


def _required_residual(value: float | None) -> float:
    if value is None:
        raise ValueError("GLRT epoch inlier omitted its required residual")
    return value
