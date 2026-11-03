"""Validate the T009 repair against existing response-only pilot CFOs."""

import gzip
import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from render_dsx01_tracks_four_to_six import measure

from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.qualified_frequency_replay import replay_qualified_frequencies

ROOT = Path(__file__).resolve().parents[1]
DEEP = ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive"


def run():
    output = DEEP / "t009_robust_order"
    recording = ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter/DSX01-S01"
    tracks = load_tracks(recording)
    archive = (
        ROOT
        / "reports/2026_10_17_continuous_track_cfo/frozen_measurements"
        / "DSX01-S01/results.json.gz"
    )
    records = json.loads(gzip.decompress(archive.read_bytes()))
    refined, replay = replay_qualified_frequencies(tracks, records)
    key = "S01-RX1-CH1-T009"
    original = next(t for t in tracks if t["key"] == key)
    updated = next(t for t in refined if t["key"] == key)
    mask = np.array(json.loads((output / "robust_orders.json").read_text())[0]["inlier_mask"])
    endpoint = next(r for r in records if r["observation_id"] == original["observation_ids"][-1])
    write(output / "endpoint_qualified_measurement.json", endpoint)
    sky = dict(np.load(DEEP / "frozen_inputs/DSX01-S01/bank.npz"))
    summaries = json.loads((output / "satellite_summary.json").read_text())
    comparison, plotted, selected_fit, overlays = [], {}, None, []
    for arm in ("c0", "fitted_c"):
        result = next(
            r for r in summaries if r["arm"] == arm and r["model"].startswith("robust_core")
        )
        if len(result["passing_candidates"]) != 1:
            raise ValueError("measurement validation requires the single reviewed candidate")
        winner = result["passing_candidates"][0]
        study = json.loads((DEEP / "cohort/DSX01-S01" / arm / "diagnosis.json").read_text())[0]
        fit = study["fit"]
        by_key = {t["key"]: t for t in tracks}
        admitted = [r for r in study["association"]["rows"] if r["compatible"]]
        if any(r["candidate_norad"] == winner["norad"] for r in admitted):
            raise ValueError("new satellite phase would require revalidating existing assignments")
        baseline_ids = {oid for r in admitted for oid in by_key[r["component"]]["observation_ids"]}
        core_ids = {oid for i, oid in enumerate(original["observation_ids"]) if mask[i]}
        if baseline_ids & core_ids:
            raise ValueError("repair would duplicate existing associated points")
        all_ids = [oid for t in tracks for oid in t["observation_ids"]]
        if len(set(all_ids)) != len(all_ids) or not core_ids <= set(all_ids):
            raise ValueError("original point ownership changed")
        overlays.append(
            dict(
                arm=arm,
                baseline_associated_points=len(baseline_ids),
                proposed_associated_points=len(baseline_ids | core_ids),
                newly_compatible_points=len(core_ids),
                original_graph_points=len(all_ids),
                proposed_associated_observation_ids=sorted(baseline_ids | core_ids),
                retained_unassociated_endpoint_id=endpoint["observation_id"],
                new_candidate=winner,
                existing_assignments_frozen=True,
                no_existing_candidate_uses_new_phase=True,
                compatibility_proposal_not_authenticated_identity=True,
                fixed_position_not_a_position_estimate=True,
            )
        )
        j = int(np.flatnonzero(sky["norad"] == winner["norad"])[0])
        subset = dict(
            time_s=sky["time_s"],
            position_km=sky["position_km"][[j]],
            velocity_km_s=sky["velocity_km_s"][[j]],
        )
        times = original["times"][mask]
        frequency, elevation = phase_frequency_grid(
            subset,
            times,
            fit["latitude_deg"],
            fit["longitude_deg"],
            phase_seconds=winner["phase_s"],
        )
        for name, track in (("original", original), ("qualified", updated)):
            core = dict(
                track,
                times=track["times"][mask],
                values=track["values"][mask],
                observation_ids=[oid for i, oid in enumerate(track["observation_ids"]) if mask[i]],
            )
            row = measure(core, frequency, elevation, np.asarray(fit["beta"]))
            write(output / f"{arm}_{name}_core_measurement.json", row)
            comparison.append(
                dict(
                    arm=arm,
                    measurement=name,
                    norad=winner["norad"],
                    points=len(times),
                    rms_hz=row["rms_hz"],
                    bias_hz=row["bias_hz"],
                    slope_hz_s=row["residual_slope_hz_s"],
                    noise=row["noise"],
                )
            )
            if arm == "fitted_c":
                plotted[name] = row
                selected_fit = fit, winner, subset
    fit, winner, subset = selected_fit
    dense = np.linspace(original["times"][0], original["times"][-1], 500)
    f, _ = phase_frequency_grid(
        subset, dense, fit["latitude_deg"], fit["longitude_deg"], phase_seconds=winner["phase_s"]
    )
    beta, g = np.asarray(fit["beta"]), matching.group(original)
    hardware = beta[g] + beta[g + 4] * (dense - 150) / 150
    if len(beta) == 9:
        hardware += beta[8] * (original["rf_hz"] / 1e9 - 11.5)
    predicted = original["rf_hz"] / 11.5e9 * f[0] + hardware + winner["bias_hz"]
    predicted -= winner["native_alias"] * matching.PERIOD
    measured = dense <= original["times"][mask][-1]
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), constrained_layout=True)
    axes[0].scatter(
        original["times"][mask],
        original["values"][mask] / 1000,
        color="#222222",
        s=25,
        label="26-point curve",
        zorder=3,
    )
    axes[0].scatter(
        original["times"][~mask],
        original["values"][~mask] / 1000,
        marker="x",
        color="#c13b32",
        s=90,
        label="Retained, unassociated endpoint",
        zorder=4,
    )
    axes[0].plot(
        dense[measured],
        predicted[measured] / 1000,
        color="#237cad",
        label=f"Calibrated Doppler · NORAD {winner['norad']}",
    )
    axes[0].plot(
        dense[~measured],
        predicted[~measured] / 1000,
        color="#237cad",
        linestyle=":",
        label="Prediction across unobserved gap",
    )
    axes[0].set(
        ylabel="Unwrapped GLRT CFO (kHz)",
        title="T009 repair · one candidate passes for the 26-point curve",
    )
    for name, color in (("original", "#237cad"), ("qualified", "#bd5919")):
        row = plotted[name]
        axes[1].plot(
            row["time_s"],
            row["residual_hz"],
            "o-",
            markersize=4,
            linewidth=0.8,
            color=color,
            label=f"{name} CFO · RMS {row['rms_hz']:.1f} Hz",
        )
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set(xlabel="Seconds from scan start", ylabel="Satellite residual (Hz)")
    for ax in axes:
        ax.legend(fontsize=8)
        ax.grid(alpha=0.2)
    fig.savefig(output / "satellite_repaired_curve.png", dpi=150)
    plt.close(fig)
    write(output / "qualified_measurement_comparison.json", comparison)
    write(output / "incremental_association_overlay.json", overlays)
    write(
        output / "measurement_validation_protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            measurement_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
            complete_original_observations_verified=replay["original_points"],
            no_observations_dropped=replay["points_dropped"] == 0,
            original_radio_only_partition_frozen=True,
            no_phase_hardware_or_identity_refit=True,
            only_component_constant_reprofiled=True,
            unsupported_or_ambiguous_measurements_retain_original_values=True,
            measurement_qualification_used_no_satellite_or_position=True,
        ),
    )
    print(json.dumps(comparison), flush=True)


if __name__ == "__main__":
    run()
