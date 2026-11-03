"""Render the next track review and isolate qualified measurement corrections."""

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
from review_dsx01_tracks_four_to_six import summarize_track

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.qualified_frequency_replay import replay_qualified_frequencies

ROOT = Path(__file__).resolve().parents[1]
DEEP = ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive"


def measure(track, frequency, elevation, beta):
    stats = matching.statistics(
        [(track["key"], [track])],
        dict(time_s=track["times"], doppler_0=frequency, elevation_deg=elevation),
        {str(track["channel"]): 0.0},
    )
    terms = profile_component_bias(stats, beta, bias_sigma_hz=1000)
    row = summarize_track(track, frequency[0], terms, 0, beta)
    g = matching.group(track)
    hardware = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
    if len(beta) == 9:
        hardware += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
    prediction = (
        track["rf_hz"] / 11.5e9 * frequency[0]
        + hardware
        + terms.bias_hz[0, 0]
        - terms.aliases[0, 0] * matching.PERIOD
    )
    row.update(
        time_s=track["times"],
        residual_hz=track["values"] - prediction,
        prediction_hz=prediction,
        original_observation_ids=track["observation_ids"],
    )
    return row


def run():
    output = DEEP / "tracks_four_to_six"
    recording = ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter/DSX01-S01"
    tracks = load_tracks(recording)
    measurement_path = (
        ROOT
        / "reports/2026_10_17_continuous_track_cfo/frozen_measurements"
        / "DSX01-S01/results.json.gz"
    )
    records = json.loads(gzip.decompress(measurement_path.read_bytes()))
    refined, replay = replay_qualified_frequencies(tracks, records)
    original_map, refined_map = ({t["key"]: t for t in rows} for rows in (tracks, refined))
    statuses = {row["observation_id"]: row["status"] for row in replay["points"]}
    sky = dict(np.load(DEEP / "frozen_inputs/DSX01-S01/bank.npz"))
    selected = [
        ("S01-RX1-CH1-T005", 69433),
        ("S01-RX1-CH1-T000", 60372),
        ("S01-RX1-CH1-T012", 64936),
    ]
    summaries, plot_rows, hashes = [], {}, {}
    for arm in ("c0", "fitted_c"):
        path = DEEP / "cohort/DSX01-S01" / arm / "diagnosis.json"
        raw = json.loads(path.read_text())[0]
        fit, old = raw["fit"], {r["component"]: r for r in raw["association"]["rows"]}
        hashes[arm] = hashlib.sha256(path.read_bytes()).hexdigest()
        for key, norad in selected:
            j = int(np.flatnonzero(sky["norad"] == norad)[0])
            subset = dict(
                time_s=sky["time_s"],
                position_km=sky["position_km"][[j]],
                velocity_km_s=sky["velocity_km_s"][[j]],
            )
            track = original_map[key]
            frequency, elevation = phase_frequency_grid(
                subset,
                track["times"],
                fit["latitude_deg"],
                fit["longitude_deg"],
                phase_seconds=fit["phases_s"][j],
            )
            pair = {}
            for name, mapping in (("original", original_map), ("qualified", refined_map)):
                row = measure(mapping[key], frequency, elevation, np.asarray(fit["beta"]))
                if name == "original":
                    assert abs(row["rms_hz"] - old[key]["rms_hz"]) < 1e-5
                pair[name] = row
            assert (
                pair["original"]["original_observation_ids"]
                == pair["qualified"]["original_observation_ids"]
            )
            changed = sum(
                statuses[oid] == "unique_qualified_frame_cfo" for oid in track["observation_ids"]
            )
            summaries.append(
                dict(
                    arm=arm,
                    component=key,
                    norad=norad,
                    points=len(track["times"]),
                    qualified_points=changed,
                    original_rms_hz=pair["original"]["rms_hz"],
                    qualified_rms_hz=pair["qualified"]["rms_hz"],
                    original_slope_hz_s=pair["original"]["residual_slope_hz_s"],
                    qualified_slope_hz_s=pair["qualified"]["residual_slope_hz_s"],
                    qualified_noise_pass=pair["qualified"]["noise"]["noise_screen_pass"],
                    qualified_bias_hz=pair["qualified"]["bias_hz"],
                )
            )
            write(output / arm / f"measurement_check_{key}.json", pair)
            if arm == "fitted_c":
                plot_rows[key] = (pair, changed)
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), constrained_layout=True)
    for ax, (key, _) in zip(axes, selected, strict=True):
        pair, changed = plot_rows[key]
        for name, color in (("original", "#237cad"), ("qualified", "#bd5919")):
            row = pair[name]
            ax.plot(
                row["time_s"],
                row["residual_hz"],
                "o-",
                color=color,
                markersize=4,
                linewidth=0.8,
                label=f"{name} CFO · RMS {row['rms_hz']:.1f} Hz · "
                f"slope {row['residual_slope_hz_s']:+.1f} Hz/s",
            )
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set(
            title=f"{key} · {changed}/{len(pair['original']['time_s'])} qualified point updates",
            xlabel="Seconds from scan start",
            ylabel="Doppler residual (Hz)",
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=9)
    fig.suptitle(
        "Frozen hardware and satellite phase · only measurement and component constant change"
    )
    fig.savefig(output / "measurement_residuals.png", dpi=150)
    plt.close(fig)

    family = json.loads((output / "fitted_c/phase_profile_64936.json").read_text())["summary"]
    candidate = family["counterfactual_shared_constant_check"]["candidates"][0]
    fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
    for i, member in enumerate(candidate["members"]):
        color = plt.get_cmap("tab10")(i)
        t, r = np.array(member["time_s"]), np.array(member["residual_hz"])
        label = member["component"].replace("S01-RX1-", "") + f" · mean {r.mean():+.0f} Hz"
        ax.plot(t, r, "o-", markersize=4, linewidth=0.7, color=color, label=label)
        ax.plot([t[0], t[-1]], [r.mean(), r.mean()], linestyle="--", linewidth=1, color=color)
    ax.axhline(0, color="black", linewidth=0.8)
    phase = family["counterfactual_phase_s"]
    count = family["counterfactual_shared_constant_check"]["points"]
    ax.set(
        xlabel="Seconds from scan start",
        ylabel="Residual under one shared constant (Hz)",
        title=f"Unsupported NORAD 64936 counterfactual · phase {phase:+.3f} s\n"
        f"{count} points · pooled RMS {candidate['rms_hz']:.1f} Hz · member checks fail",
    )
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8, ncol=2)
    fig.savefig(output / "unsupported_family_residuals.png", dpi=150)
    plt.close(fig)
    write(output / "measurement_summary.json", summaries)
    write(
        output / "measurement_protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            original_fit_sha256=hashes,
            measurement_archive_sha256=hashlib.sha256(measurement_path.read_bytes()).hexdigest(),
            original_points=replay["original_points"],
            dropped_points=replay["points_dropped"],
            no_hardware_phase_or_identity_refit=True,
            original_curvature_eligibility_unchanged=True,
            unsupported_or_ambiguous_measurements_retained=True,
            per_fragment_constant_reprofiled=True,
            measurement_qualification_did_not_use_satellites_or_position=True,
            fixed_position_diagnostic_not_localization=True,
            c0_and_fitted_c_same_measurements_candidates_times_priors_and_budget=True,
        ),
    )
    print(json.dumps(summaries), flush=True)


if __name__ == "__main__":
    run()
