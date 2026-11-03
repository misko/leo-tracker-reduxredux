"""Prepare an ordered S01 polynomial-by-polynomial satellite review."""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from compare_dsx01_graph_receivers import predict

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid

ROOT = Path(__file__).resolve().parents[1]
DEEP = ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive"
OUTPUT = DEEP / "scan1_track_review"


def run():
    OUTPUT.mkdir(exist_ok=False)
    recording = ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter/DSX01-S01"
    tracks = load_tracks(recording)
    tracks.sort(key=lambda t: (t["receiver"], t["channel"], t["times"][0], t["key"]))
    fit_path = DEEP / "cohort/DSX01-S01/fitted_c/diagnosis.json"
    study = json.loads(fit_path.read_text())[0]
    fit = study["fit"]
    old = {r["component"]: r for r in study["association"]["rows"]}
    review = {
        r["component"]: r
        for r in json.loads((DEEP / "audit/DSX01-S01/fitted_c/association.json").read_text())[
            "rows"
        ]
    }
    details = {
        r["component"]: r
        for r in json.loads(
            (DEEP / "phase_split_audit/DSX01-S01/fitted_c/rejection_detail.json").read_text()
        )
    }
    source = ROOT / "reports/2026_10_16_dsx01_fast_association_losses/context-observations.jsonl"
    originals = {
        r["observation_id"]: r
        for r in map(json.loads, source.read_text().splitlines())
        if r["source_id"] == "S01"
    }
    sky = dict(np.load("/tmp/ds22-shared-phase-bank-DSX01-S01/bank.npz"))
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    beta, phases = np.array(fit["beta"]), np.array(fit["phases_s"])
    frequency, elevation = phase_frequency_grid(
        sky, times, fit["latitude_deg"], fit["longitude_deg"], phase_seconds=phases
    )
    stats = matching.statistics(
        [(t["key"], [t]) for t in tracks],
        dict(time_s=times, doppler_0=frequency, elevation_deg=elevation),
        {str(t["channel"]): 0.0 for t in tracks},
    )
    terms = profile_component_bias(stats, beta, bias_sigma_hz=1000.0)
    records, ledger = [], []
    for fi, track in enumerate(tracks):
        key = track["key"]
        original = old[key]
        ix = np.searchsorted(times, track["times"])
        g, q = matching.group(track), track["rf_hz"] / 11.5e9
        hardware = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
        if len(beta) == 9:
            hardware += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
        candidates = []
        for j in np.argsort(terms.score[fi], kind="stable")[:3]:
            prediction = (
                q * frequency[j, ix]
                + hardware
                + terms.bias_hz[fi, j]
                - terms.aliases[fi, j] * matching.PERIOD
            )
            residual = track["values"] - prediction
            diagnostic = matching.noise_screen(residual, track["times"])
            candidates.append(
                dict(
                    norad=int(sky["norad"][j]),
                    rms_hz=float(np.sqrt(terms.residual_mse[fi, j])),
                    bias_hz=float(terms.bias_hz[fi, j]),
                    phase_s=float(phases[j]),
                    phase_prior_sigma_s=float(sky["phase_sigma_s"][j]),
                    phase_bound_s=float(sky["phase_bound_s"][j]),
                    native_alias=int(terms.aliases[fi, j]),
                    score=float(terms.score[fi, j]),
                    prediction_hz=prediction,
                    residual_hz=residual,
                    residual_diagnostics=diagnostic,
                )
            )
        assert candidates[0]["norad"] == original["candidate_norad"]
        assert abs(candidates[0]["rms_hz"] - original["rms_hz"]) < 1e-5
        poly = predict(track, track["times"])
        residual = np.array(candidates[0]["residual_hz"])
        centered = track["times"] - track["times"].mean()
        standard = [originals[oid] for oid in track["observation_ids"]]
        status = (
            "candidate compatible"
            if original["compatible"]
            else "rejected: " + ", ".join(details[key]["baseline_failed_gates"])
        )
        entry = dict(
            review_number=fi + 1,
            component=key,
            receiver=track["receiver"],
            channel=track["channel"],
            points=len(track["times"]),
            start_s=float(track["times"][0]),
            end_s=float(track["times"][-1]),
            polynomial_degrees=[p["degree"] for p in track["pieces"]],
            polynomial_rms_hz=float(np.sqrt(np.mean((track["values"] - poly) ** 2))),
            active_curvature=original["active_curvature"],
            status=status,
            candidate_norad=original["candidate_norad"],
            satellite_rms_hz=original["rms_hz"],
            residual_mean_hz=float(residual.mean()),
            residual_slope_hz_s=float(residual @ centered / (centered @ centered)),
            candidate_bias_hz=original["bias_hz"],
            candidate_phase_s=original["phase_s"],
            passing_candidate_count=len(review[key]["feasible_candidates"]),
            standard_associated_points=sum(r["original_associated"] for r in standard),
            standard_assigned_ids=dict(
                Counter(
                    str(r["original_best_satellite"]) for r in standard if r["original_associated"]
                )
            ),
            diagnostic_reason=review[key]["reason"],
        )
        ledger.append(entry)
        records.append(
            dict(
                entry,
                observations=dict(
                    time_s=track["times"], glrt_unwrapped_hz=track["values"], polynomial_hz=poly
                ),
                candidates=candidates,
                residual_diagnostics=original["residual_diagnostics"],
            )
        )
        if track["receiver"] == 1 and track["channel"] == 1:
            dense = np.linspace(track["times"][0], track["times"][-1], 400)
            jp = int(terms.best[fi])
            subset = dict(
                time_s=sky["time_s"],
                position_km=sky["position_km"][[jp]],
                velocity_km_s=sky["velocity_km_s"][[jp]],
            )
            smooth, _ = phase_frequency_grid(
                subset, dense, fit["latitude_deg"], fit["longitude_deg"], phase_seconds=phases[jp]
            )
            calibration = beta[g] + beta[g + 4] * (dense - 150) / 150
            if len(beta) == 9:
                calibration += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
            predicted = (
                q * smooth[0]
                + calibration
                + terms.bias_hz[fi, jp]
                - terms.aliases[fi, jp] * matching.PERIOD
            )
            fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True, constrained_layout=True)
            axes[0].scatter(
                track["times"],
                track["values"] / 1000,
                s=28,
                color="#222222",
                label="GLRT points · aliases unwrapped",
                zorder=4,
            )
            axes[0].plot(
                dense,
                predict(track, dense) / 1000,
                color="#888888",
                linestyle="--",
                label="Frozen polynomial",
            )
            axes[0].plot(
                dense,
                predicted / 1000,
                color="#237cad",
                label=f"Calibrated Doppler · NORAD {original['candidate_norad']}",
            )
            axes[0].set(
                ylabel="CFO (kHz)", title=f"{key} · {len(track['times'])} points · {status}"
            )
            axes[0].legend(fontsize=9)
            axes[1].scatter(
                track["times"],
                track["values"] - poly,
                s=20,
                color="#888888",
                marker="x",
                label=f"Polynomial residual · RMS {entry['polynomial_rms_hz']:.1f} Hz",
            )
            axes[1].plot(
                track["times"],
                residual,
                "o-",
                linewidth=0.8,
                markersize=4,
                color="#237cad",
                label=f"Doppler residual · RMS {original['rms_hz']:.1f} Hz",
            )
            axes[1].axhline(0, color="black", linewidth=0.8)
            axes[1].set(xlabel="Seconds from scan start", ylabel="Residual (Hz)")
            axes[1].legend(fontsize=9)
            for ax in axes:
                ax.grid(alpha=0.2)
            fig.savefig(OUTPUT / f"{key}.png", dpi=150)
            plt.close(fig)
    write(OUTPUT / "tracks.json", records)
    with (OUTPUT / "ledger.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ledger[0]))
        writer.writeheader()
        writer.writerows(ledger)
    text = [
        "# DSX01-S01: ordered polynomial track review",
        "",
        "Original Graph fragments, ordered by receiver, channel and start time. "
        "Satellite fits use the supplied GPS, per-scan/RX/band hardware and one orbital "
        "phase per NORAD. These are candidate matches, not authenticated satellite IDs.",
        "",
        "The gray curve is the frozen polynomial. Blue is physical Doppler plus the "
        "fitted shared hardware, shared satellite phase, native alias and penalized "
        "component constant. No component slope is removed. Each residual plot retains "
        "all original points. Linear fragments do not calibrate hardware or orbital phase.",
        "",
        "| Order | Track | Time s | Points | Candidate | Doppler RMS Hz | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in ledger:
        label = row["component"]
        if row["receiver"] == 1 and row["channel"] == 1:
            label = f"[{label}]({label}.png)"
        text.append(
            f"| {row['review_number']} | {label} | {row['start_s']:.2f}–{row['end_s']:.2f} | "
            f"{row['points']} | {row['candidate_norad']} | "
            f"{row['satellite_rms_hz']:.1f} | {row['status']} |"
        )
    text.extend(
        [
            "",
            "All170 tracks have metadata and their top three scored candidate residuals "
            "in tracks.json. The first lane's14 tracks have full figures. Candidate scores "
            "are research criteria, not identity probabilities. The ledger also records the "
            "frozen standard pipeline's associations on exactly these observation IDs.",
            "",
            "Current configuration: original GLRT values; drift bound ±1Hz/s, prior σ0.5Hz/s; "
            "component constant σ1000Hz and bound3000Hz; matched fitted-c arm. "
            "The known-position review does not estimate location accuracy.",
        ]
    )
    (OUTPUT / "README.md").write_text("\n".join(text) + "\n")
    write(
        OUTPUT / "protocol.json",
        dict(
            original_tracks_sha256=hashlib.sha256(
                (recording / "tracks.json").read_bytes()
            ).hexdigest(),
            input_fit_sha256=hashlib.sha256(fit_path.read_bytes()).hexdigest(),
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            all_original_points_preserved=True,
            refit=False,
            known_position=True,
            review_order="receiver/channel/start time",
            original_fragment_ids_unchanged=True,
        ),
    )
    write(
        OUTPUT / "seal.json",
        {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in OUTPUT.iterdir()
            if p.is_file()
        },
    )
    print(
        json.dumps(
            dict(
                tracks=len(records),
                points=sum(r["points"] for r in records),
                plotted=len(list(OUTPUT.glob("*.png"))),
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    run()
