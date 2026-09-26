"""Generate reversible phase replay evidence from the frozen five-dwell cache."""
import csv
import importlib.util
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
SINGLE = HERE.parents[1]
CACHE = SINGLE / "improvements/pilot-cache.npz"
METADATA = SINGLE / "improvements/pilot-cache.json"
SELECTION = SINGLE / "selection.json"
spec = importlib.util.spec_from_file_location("reversible_replay", HERE / "replay.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def main():
    cache = np.load(CACHE)
    metadata = json.loads(METADATA.read_text())
    selection = json.loads(SELECTION.read_text())
    rate = float(metadata["sample_rate_hz"])
    origin = int(selection["origin_device_counter"])
    products = cache["products"]
    weights = np.where(cache["valid"], cache["weights"], 0.0)
    cached = R.weighted_unit_mean(products, weights)
    declared_cycles = cache["correction_cycles"]
    # compare_pilot_regions removed exp(+i*declared) from RX1 at sample level.
    # This add-back defines a frame-reference gauge; it is not raw pre-average IQ.
    declared_uncorrected_gauge = cached * R.unit_phase(declared_cycles)
    tracker_cycles = np.full(len(cached), np.nan)
    tracker_segment = np.full(len(cached), -1, dtype=int)
    within_dwell_change = np.full(len(cached), np.nan)
    rows = []
    max_error = 0.0
    naive_rms = []
    frequency_by_visit = dict(zip(metadata["visit_indices"], metadata["delta_f_hz"]))
    for visit in metadata["visit_indices"]:
        indices = np.flatnonzero(cache["frame_visit_index"] == visit)
        local_time = cache["frame_time_in_dwell_s"][indices]
        predicted, segments = R.causal_previous_increment(local_time, cached[indices])
        tracker_cycles[indices] = predicted
        tracker_segment[indices] = segments
        relative, _ = R.contiguous_relative_phase(local_time, cached[indices])
        within_dwell_change[indices] = relative
        supported = np.isfinite(predicted)
        residual = np.full(len(indices), np.nan + 1j * np.nan)
        reconstructed = np.full(len(indices), np.nan + 1j * np.nan)
        correction = np.full(len(indices), np.nan + 1j * np.nan)
        residual[supported], reconstructed[supported], correction[supported] = R.reversible_derotate(
            declared_uncorrected_gauge[indices][supported],
            declared_cycles[indices][supported] + predicted[supported],
        )
        if supported.any():
            error = np.abs(reconstructed[supported] - declared_uncorrected_gauge[indices][supported])
            max_error = max(max_error, float(np.max(error)))
            naive_rms.extend(R.wrap_radians(np.angle(residual[supported]) - np.angle(declared_uncorrected_gauge[indices][supported])))
        for local, global_index in enumerate(indices):
            device_coordinate = origin + float(cache["frame_time_s"][global_index]) * rate
            ok = bool(supported[local])
            rows.append({
                "visit_index": int(visit),
                "frame_time_s": float(cache["frame_time_s"][global_index]),
                "frame_time_in_dwell_s": float(local_time[local]),
                "device_counter_coordinate": device_coordinate,
                "new_dwell_segment": bool(local == 0),
                "gap_from_previous_frame_s": (float(cache["frame_time_s"][global_index] - cache["frame_time_s"][global_index - 1])
                                              if global_index > 0 else ""),
                "tracker_segment_id": int(segments[local]),
                "declared_differential_frequency_hz": float(frequency_by_visit[visit]),
                "declared_frequency_correction_cycles": float(declared_cycles[global_index]),
                "cached_corrected_phase_deg": float(np.degrees(np.angle(cached[global_index]))),
                "declared_uncorrected_gauge_phase_deg": float(np.degrees(np.angle(declared_uncorrected_gauge[global_index]))),
                "tracker_removed_cycles": float(predicted[local]) if ok else "",
                "tracker_removed_phase_deg_wrapped": float(np.degrees(R.wrap_radians(R.TAU * predicted[local]))) if ok else "",
                "residual_phase_deg": float(np.degrees(np.angle(residual[local]))) if ok else "",
                "reconstructed_declared_gauge_phase_deg": float(np.degrees(np.angle(reconstructed[local]))) if ok else "",
                "reconstruction_abs_error": float(abs(reconstructed[local] - declared_uncorrected_gauge[global_index])) if ok else "",
                "cached_within_dwell_change_deg_processing_gauge": float(np.degrees(relative[local])),
                "supported": ok,
            })
    with (HERE / "reversible-phase.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    supported_count = int(np.isfinite(tracker_cycles).sum())
    payload = {
        "schema": "single-track-reversible-phase-replay/v1",
        "frame_count": int(len(cached)), "supported_replay_frames": supported_count,
        "unsupported_frames_after_segment_starts": int(len(cached) - supported_count),
        "max_complex_reconstruction_abs_error": max_error,
        "naive_residual_only_difference_from_input_wrapped_rms_deg": float(np.degrees(np.sqrt(np.mean(np.square(naive_rms))))),
        "coordinate_contract": {
            "cached_corrected": "conj(h0)*h1 after sample-level declared differential-CFO removal",
            "declared_uncorrected_gauge": "cached product times exp(+i*2pi*correction_cycles) at frame reference; not raw pre-average broadband product",
            "residual": "declared gauge after reversible removal of declared correction and causal tracker prediction",
            "reconstructed": "residual times both retained correction phasors; numerically identical to declared gauge",
            "within_dwell_change": "cached phase unwrapped only across observed adjacent frames and zeroed per segment; a processing-gauge diagnostic. Geometric interpretation additionally requires independent proof that the removed GLRT correction contains only instrument phase, with remaining instrument/propagation phase constant; neither is established here.",
        },
        "limitations": [
            "All reported phases are modulo 2pi unless a within-segment unwrap is explicitly named.",
            "No integer cycles are inferred across dwell or unsupported gaps.",
            "The 682 kHz-scale declared correction and tracker prediction are processing coordinates, not hardware calibration or geometric phase.",
            "No satellite-only observation can separate geometry from time-varying differential hardware or propagation phase.",
        ],
    }
    (HERE / "summary.json").write_text(json.dumps(payload, indent=2) + "\n")
    time = cache["frame_time_s"]
    fig, axes = plt.subplots(4, 1, figsize=(12, 9), sharex=True, constrained_layout=True)
    series = [(cached, "Cached corrected phase"), (declared_uncorrected_gauge, "Declared uncorrected gauge at frame reference")]
    for axis, (values, title) in zip(axes[:2], series):
        axis.scatter(time, np.degrees(np.angle(values)), s=7)
        axis.set_ylabel("phase (deg)"); axis.set_title(title)
    axes[2].scatter(time, np.degrees(R.wrap_radians(R.TAU * tracker_cycles)), s=7)
    axes[2].set(ylabel="removed (deg)", title="Causal previous-increment tracker correction (unsupported starts omitted)")
    axes[3].scatter(time, np.degrees(np.angle(declared_uncorrected_gauge)), s=8, label="input", alpha=.55)
    supported = np.isfinite(tracker_cycles)
    all_residual, all_reconstructed, _ = R.reversible_derotate(declared_uncorrected_gauge[supported], declared_cycles[supported] + tracker_cycles[supported])
    axes[3].scatter(time[supported], np.degrees(np.angle(all_reconstructed)), s=3, label="reconstructed")
    axes[3].set(xlabel="seconds from visit 259 device-counter origin", ylabel="phase (deg)", title="Exact phasor add-back", ylim=(-185,185)); axes[3].legend()
    fig.savefig(HERE / "reversible-phase.png", dpi=170)
    plt.close(fig)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
