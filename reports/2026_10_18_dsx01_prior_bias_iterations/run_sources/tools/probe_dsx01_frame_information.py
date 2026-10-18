"""Inspect existing frame-delay coherence before treating it as range evidence."""

import json
from collections import defaultdict

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from profile_dsx01_geographic_calibration import OUTPUT, incumbents
from prototype_dsx01_calibration_modes import choose_pair
from prototype_dsx01_continuous_position import CENTER, latlon

from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.sky.frames import geodetic_to_ecef_km

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def range_seconds(scan, j, times, point):
    p, _ = paired_phase_states(
        scan.sky, np.asarray(times), np.full(len(times), j), np.zeros(len(scan.norads))
    )
    site = geodetic_to_ecef_km(*point, 0.0)
    return np.linalg.norm(p - site, axis=1) / 299792.458


def detrend(values, times):
    design = np.column_stack((np.ones(len(times)), np.asarray(times) - np.mean(times)))
    return values - design @ np.linalg.lstsq(design, values, rcond=None)[0]


def run(case="DSX01-S05"):
    data = json.loads((OUTPUT / "frame_epochs.json").read_text())[case]["epochs"]
    scan = Scan(case)
    _, pair = choose_pair(incumbents(case, "receiver_smooth"))
    fit = pair["c0"]
    lookup = {t["key"]: t for t in scan.tracks}
    groups = defaultdict(dict)
    for row in fit["rows"]:
        if not row["active_curvature"]:
            continue
        track = lookup[row["component"]]
        key = (row["candidate_index"], track["receiver"], track["channel"])
        for oid in track["observation_ids"]:
            groups[key][oid] = data[oid]
    period = 1 / 750
    records = []
    figure, axes = plt.subplots(2, 2, figsize=(15, 9), constrained_layout=True)
    colors = plt.get_cmap("tab20")
    for group_number, ((j, rx, ch), observations) in enumerate(groups.items()):
        rows = sorted(observations.values(), key=lambda r: r["frame_epoch_elapsed_s"])
        times = np.array([r["frame_epoch_elapsed_s"] for r in rows])
        measured = np.array([r["frame_phase_modulo_s"] for r in rows])
        prediction = range_seconds(scan, j, times, CENTER)
        corrected = (measured - prediction + period / 2) % period - period / 2
        unwrapped = np.unwrap(2 * np.pi * corrected / period) * period / (2 * np.pi)
        if len(times) < 12:
            continue
        axes[0, 0].scatter(times, measured * 1e6, s=3, color=colors(group_number % 20), alpha=0.5)
        # Limit the initial diagnostic to short contiguous runs, without
        # assuming that a frame clock survives a beam assignment gap.
        cuts = np.flatnonzero(np.diff(times) > 3) + 1
        for index in np.split(np.arange(len(times)), cuts):
            if len(index) < 12 or np.ptp(times[index]) < 10:
                continue
            t = times[index]
            residual = detrend(unwrapped[index], t)
            rms = float(np.sqrt(np.mean(residual**2)))
            signals = []
            for delta in ((1, 0), (0, 1)):
                shifted = range_seconds(scan, j, t, latlon(delta))
                signals.append(
                    float(np.sqrt(np.mean(detrend(shifted - prediction[index], t) ** 2)))
                )
            records.append(
                dict(
                    norad=int(scan.norads[j]),
                    receiver=rx,
                    channel=ch,
                    points=len(index),
                    start_s=float(t[0]),
                    end_s=float(t[-1]),
                    affine_removed_rms_ns=rms * 1e9,
                    east_1km_affine_removed_signal_ns=signals[0] * 1e9,
                    north_1km_affine_removed_signal_ns=signals[1] * 1e9,
                    rough_east_shape_SNR_1km=signals[0] * np.sqrt(len(index)) / max(rms, 1e-12),
                    rough_north_shape_SNR_1km=signals[1] * np.sqrt(len(index)) / max(rms, 1e-12),
                )
            )
            axes[0, 1].plot(
                t,
                residual * 1e6,
                ".-",
                markersize=2,
                linewidth=0.4,
                color=colors(group_number % 20),
                alpha=0.6,
            )
    axes[0, 0].set(
        title="Existing measured frame phase",
        xlabel="Elapsed device time (s)",
        ylabel="Frame phase modulo 1/750 s (µs)",
    )
    axes[0, 1].set(
        title="Nominal causal range removed at blind town centre",
        xlabel="Elapsed device time (s)",
        ylabel="Per-run affine residual (µs)",
    )
    if records:
        axes[1, 0].hist(np.log10([r["affine_removed_rms_ns"] for r in records]), bins=25)
        axes[1, 1].scatter(
            [r["east_1km_affine_removed_signal_ns"] for r in records],
            [r["affine_removed_rms_ns"] for r in records],
            label="East",
            s=12,
        )
        axes[1, 1].scatter(
            [r["north_1km_affine_removed_signal_ns"] for r in records],
            [r["affine_removed_rms_ns"] for r in records],
            label="North",
            s=12,
        )
        axes[1, 1].set(xscale="log", yscale="log")
        axes[1, 1].legend()
    axes[1, 0].set(xlabel="log10 affine-residual RMS (ns)", ylabel="Contiguous runs")
    axes[1, 1].set(
        xlabel="Affine-removed geometric signal for 1 km (ns)",
        ylabel="Measured affine-residual RMS (ns)",
    )
    figure.savefig(OUTPUT / "frame_information_diagnostic.png", dpi=160)
    plt.close(figure)
    write(
        OUTPUT / "frame_information_diagnostic.json",
        dict(
            case=case,
            nominal_position=CENTER,
            original_causal_TLE_phase_zero=True,
            instantaneous_range_diagnostic_not_validated_pseudorange=True,
            arbitrary_affine_frame_clock_removed_per_run=True,
            max_gap_s=3,
            min_points=12,
            min_span_s=10,
            associations_are_unverified_CFO_hypotheses=True,
            records=records,
        ),
    )
    print(
        "runs",
        len(records),
        "median timing RMS ns",
        np.median([r["affine_removed_rms_ns"] for r in records]),
        flush=True,
    )
    return records


if __name__ == "__main__":
    run()
