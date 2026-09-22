"""Compare constant-phase profiles across frozen visits from one shared RF track."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from scipy.signal import fftconvolve, firwin

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from leo.analysis.starlink.broadband_alignment import estimate_broadband_alignment
from leo.analysis.starlink.broadband_phase_tracking import frequency_held_out_tracking
from report_broadband_alignment import frozen_edge_evidence

from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore

SESSION = "scan-hop-e46d3aba244cf641"
VISITS = (376, 453, 486, 513, 537, 564, 588, 614, 638, 668, 697, 724)
RATE = 2_500_000
WINDOW_SAMPLES = 5_000
STRIDE_SAMPLES = 1_250
PHASE = np.linspace(-np.pi, np.pi, 721)


def compensate(iq, model):
    sample = np.arange(len(iq), dtype=float)
    time = (sample - model.reference_sample) / RATE
    y = iq[:, 1] * np.exp(
        -2j * np.pi * (model.relative_cfo_hz * time + model.relative_cfo_rate_hz_s * time**2 / 2)
    )
    n = np.arange(-32, 33)
    taps = np.sinc(n + model.fractional_delay_samples) * np.hanning(65)
    taps /= taps.sum()
    y = fftconvolve(y, taps, mode="same")
    return np.column_stack((iq[:, 0], y))


def common_band(iq):
    low, high = -500_000.0, 1_175_000.0
    center, halfwidth = (low + high) / 2, (high - low) / 2
    taps = firwin(513, halfwidth, fs=RATE)
    taps = taps * np.exp(2j * np.pi * center * (np.arange(513) - 256) / RATE)
    return np.column_stack([fftconvolve(iq[:, receiver], taps, mode="same") for receiver in (0, 1)])


def check_compensation_sign():
    sample = np.arange(10_000, dtype=float)
    signal_frequency = 123_456.0
    relative_frequency = -675_400.0
    delay = 2.375
    phase = 0.71
    x = np.exp(2j * np.pi * signal_frequency * sample / RATE)
    y = np.exp(
        2j * np.pi * signal_frequency * (sample - delay) / RATE
        + 2j * np.pi * relative_frequency * sample / RATE
        + 1j * phase
    )
    model = type(
        "KnownModel",
        (),
        {
            "reference_sample": 0.0,
            "relative_cfo_hz": relative_frequency,
            "relative_cfo_rate_hz_s": 0.0,
            "fractional_delay_samples": delay,
        },
    )()
    aligned = compensate(np.column_stack((x, y)), model)
    error = np.angle(aligned[100:-100, 1] * aligned[100:-100, 0].conj() * np.exp(-1j * phase))
    assert np.max(abs(error)) < 1e-4


def time_windows(values):
    starts = np.arange(2_500, len(values) - WINDOW_SAMPLES - 2_500 + 1, STRIDE_SAMPLES)
    output = []
    profiles = []
    for start in starts:
        stop = start + WINDOW_SAMPLES
        cross = values[start:stop, 1] * values[start:stop, 0].conj()
        cross_sum = np.sum(cross)
        power0 = float(np.sum(abs(values[start:stop, 0]) ** 2))
        power1 = float(np.sum(abs(values[start:stop, 1]) ** 2))
        coherence = float(abs(cross_sum) / np.sqrt(power0 * power1))
        phase = float(np.angle(cross_sum))
        groups = np.array_split(np.arange(WINDOW_SAMPLES), 10)
        delete_phase = np.asarray([np.angle(cross_sum - np.sum(cross[group])) for group in groups])
        delta = np.angle(np.exp(1j * (delete_phase - phase)))
        phase_se = float(np.sqrt(9 / 10 * np.sum(delta**2)))
        center = start + (WINDOW_SAMPLES - 1) / 2
        output.append(
            {
                "start_sample": int(start),
                "stop_sample_exclusive": int(stop),
                "center_time_ms": float(center / RATE * 1_000),
                "phase_deg": float(np.degrees(phase)),
                "coherence": coherence,
                "minimum_prediction_error": float(np.sqrt(max(0.0, 1 - coherence**2))),
                "conditional_phase_jackknife_se_deg": float(np.degrees(phase_se)),
            }
        )
        profiles.append(coherence * np.cos(PHASE - phase))
    return output, np.asarray(profiles).T


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check_compensation_sign()
    args.output.mkdir(parents=True, exist_ok=True)

    evidence = frozen_edge_evidence("e46d3aba244cf641")
    selected = tuple(evidence["selected_visit_indexes"])
    assert selected == VISITS
    by_visit = {row["visit_index"]: row for row in evidence["visits"]}
    assert all(
        by_visit[index]["target_index"] == 5
        and by_visit[index]["phase_blind_pair_count"] == 1
        and len(by_visit[index]["corrected_pairs"]) == 1
        for index in VISITS
    )
    inventory_path = (
        args.research_root
        / "reports/figures/2026_09_21_recent8h_track_inventory/top5_dual_shared_visits.json"
    )
    inventory = json.loads(inventory_path.read_text())
    track = next(row for row in inventory["pairs"] if row["session_id"] == SESSION)
    assert track["channel"] == 2 and track["edge"] == "upper"
    assert all(index in track["shared_visit_indices"] for index in VISITS)
    assert track["input_manifest_sha256"] == evidence["input_manifest_sha256"]

    rows = []
    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    with AdaptiveHopAnalysisInputStore(store).source(SESSION) as source:
        assert source.input_manifest_sha256 == evidence["input_manifest_sha256"]
        first_counter = source.visits[VISITS[0]].event.valid_start_counter
        for visit_index in VISITS:
            iq = source.read_visit(visit_index)
            seed = by_visit[visit_index]["train_peak"]["frequency_hz"]
            alignment = estimate_broadband_alignment(
                iq,
                RATE,
                receiver_cfo_seed_hz=seed,
                cfo_search_half_width_hz=2_000,
            )
            tracking = frequency_held_out_tracking(iq, RATE, alignment.model)
            values = common_band(compensate(iq, alignment.model))
            windows, profile = time_windows(values)
            event = source.visits[visit_index].event
            rows.append(
                {
                    "visit_index": visit_index,
                    "target_index": event.target_index,
                    "track_elapsed_s": (event.valid_start_counter - first_counter) / RATE,
                    "seed_frequency_hz": seed,
                    "model": {
                        "reference_sample": alignment.model.reference_sample,
                        "relative_cfo_hz": alignment.model.relative_cfo_hz,
                        "relative_cfo_rate_hz_s": alignment.model.relative_cfo_rate_hz_s,
                        "fractional_delay_samples": alignment.model.fractional_delay_samples,
                        "phase_rad": alignment.model.phase_rad,
                        "phase_standard_error_rad": alignment.model.phase_standard_error_rad,
                        "frequency_reference_hz": alignment.model.frequency_reference_hz,
                        "phase_uncertainty_kind": alignment.model.uncertainty_kind,
                        "selected_bandwidth_hz": (
                            max(alignment.model.frequency_hz) - min(alignment.model.frequency_hz)
                        ),
                    },
                    "edge_pair": by_visit[visit_index]["corrected_pairs"][0],
                    "frequency_held_out_tracking": tracking,
                    "windows": windows,
                    "profile": profile,
                }
            )

    global_limit = max(float(np.max(abs(row["profile"]))) for row in rows)
    fig, axes = plt.subplots(4, 3, figsize=(15, 13), sharex=True, sharey=True)
    image = None
    for ax, row in zip(axes.flat, rows, strict=True):
        centers = np.asarray([window["center_time_ms"] for window in row["windows"]])
        phases = np.asarray([window["phase_deg"] for window in row["windows"]])
        image = ax.pcolormesh(
            centers,
            np.degrees(PHASE),
            row["profile"],
            shading="nearest",
            cmap="coolwarm",
            vmin=-global_limit,
            vmax=global_limit,
            rasterized=True,
        )
        ax.scatter(centers, phases, s=2.5, color="black", alpha=0.75)
        ax.axvline(60, color="black", linestyle="--", alpha=0.55)
        median_coherence = np.median([window["coherence"] for window in row["windows"]])
        ax.set_title(
            f"visit {row['visit_index']}  •  track +{row['track_elapsed_s']:.1f} s"
            f"  •  median ρ {median_coherence:.3f}"
        )
        ax.set_xlim(2, 118)
        ax.set_ylim(-180, 180)
        ax.set_yticks((-180, -90, 0, 90, 180))
    for ax in axes[-1, :]:
        ax.set_xlabel("Time in 120 ms dwell (ms)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Candidate phase (degrees)")
    assert image is not None
    colorbar_axis = fig.add_axes((0.91, 0.12, 0.018, 0.75))
    colorbar = fig.colorbar(image, cax=colorbar_axis)
    colorbar.set_label("Signed coherence")
    fig.suptitle(
        "RX1 − RX0 constant-phase profiles across one shared RF track\n"
        "2 ms windows / 0.5 ms stride; each panel is an independently retuned dwell",
        y=0.995,
    )
    fig.subplots_adjust(left=0.07, right=0.88, bottom=0.06, top=0.94, hspace=0.24, wspace=0.08)
    fig.savefig(args.output / "multi-dwell-phase-heatmaps.png", dpi=180)
    plt.close(fig)

    summary = []
    for row in rows:
        coherence = np.asarray([window["coherence"] for window in row["windows"]])
        phase = np.unwrap(np.radians([window["phase_deg"] for window in row["windows"]]))
        time = np.asarray([window["center_time_ms"] for window in row["windows"]]) / 1_000
        slope, intercept = np.polyfit(time, phase, 1)
        residual = np.angle(np.exp(1j * (phase - (slope * time + intercept))))
        summary.append(
            {
                "visit_index": row["visit_index"],
                "track_elapsed_s": row["track_elapsed_s"],
                "median_coherence": float(np.median(coherence)),
                "minimum_coherence": float(np.min(coherence)),
                "maximum_coherence": float(np.max(coherence)),
                "median_minimum_prediction_error": float(np.median(np.sqrt(1 - coherence**2))),
                "linear_residual_frequency_hz": float(slope / (2 * np.pi)),
                "linear_phase_fit_circular_rms_deg": float(
                    np.degrees(np.sqrt(np.mean(residual**2)))
                ),
                "median_conditional_phase_se_deg": float(
                    np.median(
                        [window["conditional_phase_jackknife_se_deg"] for window in row["windows"]]
                    )
                ),
                "edge_pilot_phase_deg": float(np.degrees(row["edge_pair"]["phase_rad"])),
                "edge_pilot_phase_se_deg": row["edge_pair"]["phase_standard_error_deg"],
                "broadband_intercept_phase_deg": float(np.degrees(row["model"]["phase_rad"])),
                "broadband_intercept_phase_se_deg": float(
                    np.degrees(row["model"]["phase_standard_error_rad"])
                ),
                "frequency_held_out_tracked_coherence": row["frequency_held_out_tracking"][
                    "tracked"
                ]["coherence"],
                "frequency_held_out_residual_phase_deg": float(
                    np.degrees(row["frequency_held_out_tracking"]["tracked"]["phase_rad"])
                ),
                "frequency_held_out_wrong_time_coherence": row["frequency_held_out_tracking"][
                    "wrong_time"
                ]["coherence"],
                **row["model"],
            }
        )
    elapsed = np.asarray([row["track_elapsed_s"] for row in summary])
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    axes[0].plot(elapsed, [row["median_coherence"] for row in summary], "o-")
    axes[0].set_ylabel("Median coherence")
    axes[1].plot(elapsed, [row["linear_residual_frequency_hz"] for row in summary], "o-")
    axes[1].axhline(0, color="black", alpha=0.4)
    axes[1].set_ylabel("Within-dwell residual\nfrequency (Hz)")
    axes[2].plot(elapsed, [row["linear_phase_fit_circular_rms_deg"] for row in summary], "o-")
    axes[2].set(
        xlabel="Elapsed time along shared track (s)", ylabel="Linear phase fit\nRMS (degrees)"
    )
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.suptitle(
        "Per-dwell common-signal metrics along the 44.3 s shared track\n"
        "phase intercepts are not connected across retunes"
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(args.output / "multi-dwell-summary.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(4, 3, figsize=(15, 13), sharex=True, sharey=True)
    method_handles = None
    for ax, row in zip(axes.flat, rows, strict=True):
        centers = np.asarray([window["center_time_ms"] for window in row["windows"]])
        rolling = np.asarray([window["phase_deg"] for window in row["windows"]])
        scalar = ax.scatter(
            centers,
            rolling,
            s=3,
            color="black",
            alpha=0.55,
            label="Common-band scalar",
        )
        broadband = ax.errorbar(
            row["model"]["reference_sample"] / RATE * 1_000,
            np.degrees(row["model"]["phase_rad"]),
            yerr=np.degrees(row["model"]["phase_standard_error_rad"]),
            fmt="s",
            color="tab:blue",
            markersize=5,
            capsize=2,
            label="Broadband intercept",
        )
        edge = row["edge_pair"]
        pilot = ax.errorbar(
            edge["center_sample"] / RATE * 1_000,
            np.degrees(edge["phase_rad"]),
            yerr=edge["phase_standard_error_deg"],
            fmt="^",
            color="tab:red",
            markersize=5,
            capsize=2,
            label="Edge pilot",
        )
        tracker_rows = row["frequency_held_out_tracking"]["rows"]
        tracker_time = np.asarray([item["center_sample"] / RATE * 1_000 for item in tracker_rows])
        tracker_a_residual = np.asarray([item["training_band_phase_rad"] for item in tracker_rows])
        tracker_b_residual = np.asarray(
            [item["held_band_residual_phase_rad"] for item in tracker_rows]
        )
        tracker_a = np.degrees(
            np.angle(np.exp(1j * (row["model"]["phase_rad"] + tracker_a_residual)))
        )
        tracker_b = np.degrees(
            np.angle(
                np.exp(1j * (row["model"]["phase_rad"] + tracker_a_residual + tracker_b_residual))
            )
        )
        tracked_a = ax.scatter(
            tracker_time,
            tracker_a,
            s=9,
            marker="o",
            color="tab:green",
            label="A-band tracked broadband gauge",
        )
        tracked_b = ax.scatter(
            tracker_time,
            tracker_b,
            s=10,
            marker="x",
            color="tab:purple",
            label="B-band inferred broadband gauge",
        )
        ax.axvline(60, color="black", linestyle="--", alpha=0.4)
        ax.set_title(f"visit {row['visit_index']}  •  track +{row['track_elapsed_s']:.1f} s")
        ax.set_xlim(2, 118)
        ax.set_ylim(-180, 180)
        ax.set_yticks((-180, -90, 0, 90, 180))
        if method_handles is None:
            method_handles = (scalar, broadband, pilot, tracked_a, tracked_b)
    for ax in axes[-1, :]:
        ax.set_xlabel("Time in 120 ms dwell (ms)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Native wrapped phase (degrees)")
    assert method_handles is not None
    fig.legend(
        method_handles,
        [
            "Common-band scalar",
            "Broadband intercept",
            "Edge pilot",
            "A-band tracked broadband gauge",
            "B-band inferred broadband gauge",
        ],
        loc="upper center",
        ncol=3,
        bbox_to_anchor=(0.5, 0.962),
    )
    fig.suptitle(
        "Native phase observables from four methods on the same shared-track dwells\n"
        "absolute offsets between method gauges are not physical disagreement",
        y=0.995,
    )
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.06, top=0.90, hspace=0.24, wspace=0.08)
    fig.savefig(args.output / "multi-method-phase-comparison.png", dpi=180)
    plt.close(fig)

    csv_rows = []
    for row in rows:
        for window in row["windows"]:
            csv_rows.append(
                (
                    row["visit_index"],
                    row["track_elapsed_s"],
                    window["center_time_ms"],
                    window["phase_deg"],
                    window["coherence"],
                    window["minimum_prediction_error"],
                    window["conditional_phase_jackknife_se_deg"],
                )
            )
    np.savetxt(
        args.output / "multi-dwell-windows.csv",
        np.asarray(csv_rows),
        delimiter=",",
        fmt="%.12g",
        header=(
            "visit_index,track_elapsed_s,dwell_center_time_ms,"
            "most_likely_rx1_minus_rx0_phase_deg,coherence_magnitude,"
            "minimum_normalized_prediction_error,conditional_phase_jackknife_se_deg"
        ),
        comments="",
    )
    method_rows = np.asarray(
        [
            (
                row["visit_index"],
                row["track_elapsed_s"],
                row["edge_pilot_phase_deg"],
                row["edge_pilot_phase_se_deg"],
                row["broadband_intercept_phase_deg"],
                row["broadband_intercept_phase_se_deg"],
                row["frequency_held_out_tracked_coherence"],
                row["frequency_held_out_wrong_time_coherence"],
                row["frequency_held_out_residual_phase_deg"],
            )
            for row in summary
        ]
    )
    np.savetxt(
        args.output / "multi-method-summary.csv",
        method_rows,
        delimiter=",",
        fmt="%.12g",
        header=(
            "visit_index,track_elapsed_s,edge_pilot_phase_deg,edge_pilot_phase_se_deg,"
            "broadband_intercept_phase_deg,broadband_intercept_phase_se_deg,"
            "frequency_held_out_tracked_coherence,frequency_held_out_wrong_time_coherence,"
            "frequency_held_out_residual_phase_deg"
        ),
        comments="",
    )
    document = {
        "schema_version": 1,
        "kind": "shared_track_multi_dwell_constant_phase_profiles",
        "session_id": SESSION,
        "input_manifest_sha256": evidence["input_manifest_sha256"],
        "tracking_manifest_sha256": track["analysis_manifest_sha256"],
        "raw_recording_authority_digest": track["raw_recording_authority_digest"],
        "channel": track["channel"],
        "edge": track["edge"],
        "receiver_tracklet_ids": track["track_ids"],
        "receiver_tracklet_observation_counts": track["track_observation_counts"],
        "shared_track_visit_count": track["shared_visit_count"],
        "selected_visits": list(VISITS),
        "selection_authority": "frozen prior raw-coherence replay; no phase-result selection",
        "window_samples": WINDOW_SAMPLES,
        "window_duration_ms": WINDOW_SAMPLES / RATE * 1_000,
        "window_stride_ms": STRIDE_SAMPLES / RATE * 1_000,
        "phase_grid_step_deg": float(np.degrees(PHASE[1] - PHASE[0])),
        "common_bandpass_hz": [-500_000.0, 1_175_000.0],
        "channel_response_equalized": False,
        "retune_phase_continuity_claimed": False,
        "satellite_identity_claimed": False,
        "summary": summary,
        "visits": [{key: value for key, value in row.items() if key != "profile"} for row in rows],
        "source_hashes": {
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "frozen_phase_evidence_sha256": hashlib.sha256(
                (
                    args.research_root / "reports/figures/2026_09_21_recent8h_phase_replay/"
                    "scan-hop-e46d3aba244cf641.raw-coherence.json"
                ).read_bytes()
            ).hexdigest(),
            "track_inventory_sha256": hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
        },
    }
    (args.output / "multi-dwell-results.json").write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
