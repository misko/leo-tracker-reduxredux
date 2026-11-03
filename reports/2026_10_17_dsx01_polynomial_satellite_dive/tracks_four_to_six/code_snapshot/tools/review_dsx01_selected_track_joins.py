"""Frozen-calibration, all-candidate shared-constant checks for the first tracks.

These checks do not change the admitted population, calibration or orbit phase.
They test whether proposed continuations can remove an independent constant.
"""

import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from associate_merged_track_catalogue import load_tracks, write

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

ROOT = Path(__file__).resolve().parents[1]
DEEP = ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive"
NOISE_HZ = 150.0


def shared_alias_frame(values, alias, reference_alias):
    """Lift original CFO values to a common integer branch for display only."""
    return np.asarray(values) + (alias - reference_alias) * matching.PERIOD


def evaluate_join(tracks, times, frequency, elevation, beta, norad, phase_allowed, supported):
    """Compare every candidate with one constant, retaining each original alias.

    Both every-member and time-sorted pooled residuals must pass. A positive
    separate-minus-joint integrated Gaussian cost favors removing constants;
    it is not an identity probability. Candidate labels and geometry are inputs.
    """
    if not tracks or any(len(t["times"]) < 4 for t in tracks):
        raise ValueError("nonempty fragments with at least four points required")
    ids = [oid for t in tracks for oid in t["observation_ids"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate observation ownership")
    bank = dict(time_s=times, doppler_0=frequency, elevation_deg=elevation)
    corrections = {str(t["channel"]): 0.0 for t in tracks}
    joined = matching.statistics([("joint", tracks)], bank, corrections)
    separate = matching.statistics([(t["key"], [t]) for t in tracks], bank, corrections)
    terms = profile_component_bias(joined, beta, bias_sigma_hz=1000.0)
    independent = profile_component_bias(separate, beta, bias_sigma_hz=1000.0)
    passed = joined["component_visible"][0] & phase_allowed
    passed &= (np.abs(terms.bias_hz[0]) <= 3000) & (terms.residual_mse[0] <= 450**2)
    residuals, predictions, member_diagnostics = [], [], []
    for fi, track in enumerate(tracks):
        ix = np.searchsorted(times, track["times"])
        if not np.array_equal(times[ix], track["times"]):
            raise ValueError("geometry must contain every original observation time")
        g, q = matching.group(track), track["rf_hz"] / 11.5e9
        hardware = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
        if len(beta) == 9:
            hardware += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
        predicted = (
            q * frequency[:, ix]
            + hardware[None, :]
            + terms.bias_hz[0, :, None]
            - terms.aliases[fi, :, None] * matching.PERIOD
        )
        residual = track["values"][None, :] - predicted
        diagnostic = batch_noise_screen(residual, track["times"])
        passed &= diagnostic["noise_screen_pass"] & supported[g]
        passed &= np.mean(residual**2, axis=1) <= 450**2
        residuals.append(residual)
        predictions.append(predicted)
        member_diagnostics.append(diagnostic)
    observed_times = np.concatenate([t["times"] for t in tracks])
    order = np.argsort(observed_times, kind="stable")
    pooled = np.concatenate(residuals, axis=1)[:, order]
    pooled_diagnostics = batch_noise_screen(pooled, observed_times[order])
    passed &= pooled_diagnostics["noise_screen_pass"]
    # score is cost in Hz^2 per observation; restore its integrated dimensionless cost.
    counts = np.array([len(t["times"]) for t in tracks])
    independent_cost = np.sum(independent.score * counts[:, None], axis=0) / NOISE_HZ**2
    joint_cost = len(ids) * terms.score[0] / NOISE_HZ**2
    gain = independent_cost - joint_cost
    feasible = np.flatnonzero(passed)
    ranked = feasible[np.argsort(terms.score[0, feasible], kind="stable")]
    shown = list(dict.fromkeys([*ranked.tolist(), *np.argsort(terms.score[0])[:3].tolist()]))
    candidates = []
    for j in shown:
        candidates.append(
            dict(
                norad=int(norad[j]),
                passes_all_gates=bool(passed[j]),
                rms_hz=float(np.sqrt(terms.residual_mse[0, j])),
                bias_hz=float(terms.bias_hz[0, j]),
                native_aliases=terms.aliases[:, j],
                separate_minus_joined_cost=float(gain[j]),
                score=float(terms.score[0, j]),
                pooled_diagnostics={k: v[j] for k, v in pooled_diagnostics.items()},
                members=[
                    dict(
                        component=t["key"],
                        points=len(t["times"]),
                        time_s=t["times"],
                        observed_hz=t["values"],
                        predicted_hz=predictions[fi][j],
                        residual_hz=residuals[fi][j],
                        rms_hz=float(np.sqrt(np.mean(residuals[fi][j] ** 2))),
                        diagnostics={k: v[j] for k, v in member_diagnostics[fi].items()},
                    )
                    for fi, t in enumerate(tracks)
                ],
            )
        )
    return dict(
        members=[t["key"] for t in tracks],
        points=len(ids),
        candidate_count=len(norad),
        passing_candidates=norad[ranked],
        best_passing_candidate=int(norad[ranked[0]]) if len(ranked) else None,
        join_favored=bool(len(ranked) and gain[ranked[0]] > 0),
        candidates=candidates,
    )


def plot_continuation(result, sky, fit, tracks, path):
    row = result["candidates"][0]
    j = int(np.flatnonzero(sky["norad"] == row["norad"])[0])
    dense = np.linspace(
        min(t["times"][0] for t in tracks), max(t["times"][-1] for t in tracks), 600
    )
    subset = dict(
        time_s=sky["time_s"],
        position_km=sky["position_km"][[j]],
        velocity_km_s=sky["velocity_km_s"][[j]],
    )
    frequency, _ = phase_frequency_grid(
        subset,
        dense,
        fit["latitude_deg"],
        fit["longitude_deg"],
        phase_seconds=fit["phases_s"][j],
    )
    beta = np.asarray(fit["beta"])
    g, rf = matching.group(tracks[0]), tracks[0]["rf_hz"]
    hardware = beta[g] + beta[g + 4] * (dense - 150) / 150
    if len(beta) == 9:
        hardware += beta[8] * (rf / 1e9 - 11.5)
    prediction = (
        rf / 11.5e9 * frequency[0]
        + hardware
        + row["bias_hz"]
        - row["native_aliases"][0] * matching.PERIOD
    )
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True, constrained_layout=True)
    axes[0].plot(dense, prediction / 1000, color="#777777", label="One calibrated satellite curve")
    for i, member in enumerate(row["members"]):
        color = ("#237cad", "#bd5919")[i]
        label = member["component"].split("-")[-1]
        lift = int(row["native_aliases"][i] - row["native_aliases"][0])
        if lift:
            label += f" (alias lift {lift:+d} × P)"
        displayed = shared_alias_frame(
            member["observed_hz"], row["native_aliases"][i], row["native_aliases"][0]
        )
        axes[0].scatter(
            member["time_s"],
            displayed / 1000,
            s=24,
            color=color,
            label=label,
            zorder=3,
        )
        axes[1].plot(
            member["time_s"],
            member["residual_hz"],
            "o-",
            color=color,
            markersize=4,
            linewidth=0.8,
            label=label,
        )
    lo, hi = tracks[0]["times"][-1], tracks[1]["times"][0]
    for ax in axes:
        ax.axvspan(
            lo, hi, color="#dddddd", alpha=0.5, label="Unobserved gap" if ax == axes[0] else None
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=9)
    axes[0].set(
        ylabel="GLRT CFO in common alias frame (kHz)",
        title=f"T008 + T011 · NORAD {row['norad']} · one constant · {row['rms_hz']:.1f} Hz RMS",
    )
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set(xlabel="Seconds from scan start", ylabel="Residual (Hz)")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def run():
    output = DEEP / "first_track_join_checks_v2"
    output.mkdir(exist_ok=False)
    recording = ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter/DSX01-S01"
    mapping = {t["key"]: t for t in load_tracks(recording)}
    source = Path("/tmp/ds22-shared-phase-bank-DSX01-S01")
    sky = dict(np.load(source / "bank.npz"))
    pairs = dict(
        same_channel_continuation=["S01-RX1-CH1-T008", "S01-RX1-CH1-T011"],
        same_candidate_cross_receiver=["S01-RX1-CH1-T004", "S01-RX2-CH1-T004"],
        same_candidate_cross_band=["S01-RX1-CH1-T008", "S01-RX1-CH6-T004"],
        different_candidate_overlap_control=["S01-RX1-CH1-T008", "S01-RX1-CH1-T004"],
    )
    times = np.unique(
        np.concatenate([mapping[k]["times"] for keys in pairs.values() for k in keys])
    )
    summaries, inputs = [], {}
    for arm in ("c0", "fitted_c"):
        path = DEEP / "cohort/DSX01-S01" / arm / "diagnosis.json"
        raw = json.loads(path.read_text())[0]
        fit, association = raw["fit"], raw["association"]
        inputs[arm] = hashlib.sha256(path.read_bytes()).hexdigest()
        supported = np.zeros(4, bool)
        phase_ids = set()
        for row in association["rows"]:
            if row["compatible"] and row["active_curvature"]:
                supported[matching.group(mapping[row["component"]])] = True
                phase_ids.add(row["candidate_norad"])
        allowed = (np.abs(fit["phases_s"]) <= 1e-3) | np.isin(sky["norad"], list(phase_ids))
        frequency, elevation = phase_frequency_grid(
            sky,
            times,
            fit["latitude_deg"],
            fit["longitude_deg"],
            phase_seconds=np.asarray(fit["phases_s"]),
        )
        for label, keys in pairs.items():
            tracks = [mapping[k] for k in keys]
            result = evaluate_join(
                tracks,
                times,
                frequency,
                elevation,
                np.asarray(fit["beta"]),
                sky["norad"],
                allowed,
                supported,
            )
            write(output / f"{arm}_{label}.json", result)
            summaries.append(
                dict(
                    arm=arm,
                    check=label,
                    **{
                        k: result[k]
                        for k in (
                            "points",
                            "candidate_count",
                            "passing_candidates",
                            "best_passing_candidate",
                            "join_favored",
                        )
                    },
                )
            )
            if label == "same_channel_continuation" and result["join_favored"]:
                plot_continuation(result, sky, fit, tracks, output / f"{arm}_{label}.png")
    write(output / "summary.json", summaries)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            input_fit_sha256=inputs,
            bank_sha256=hashlib.sha256((source / "bank.npz").read_bytes()).hexdigest(),
            original_tracks_sha256=hashlib.sha256(
                (recording / "tracks.json").read_bytes()
            ).hexdigest(),
            known_position=True,
            no_calibration_or_phase_refit=True,
            no_component_slope=True,
            one_constant_per_join=True,
            every_original_point_preserved=True,
            all_candidates_considered=True,
            both_member_and_pooled_noise_screen=True,
            c0_and_fitted_c_matched_pairs_candidates_and_gates=True,
            continuation_gap_s=float(
                mapping[pairs["same_channel_continuation"][1]]["times"][0]
                - mapping[pairs["same_channel_continuation"][0]]["times"][-1]
            ),
            existing_automatic_merge_gap_s=10,
            diagnostic_only_admitted_population_unchanged=True,
            phase_and_hardware_inputs_include_reviewed_curved_tracks=True,
            not_independent_identity_or_position_validation=True,
        ),
    )
    print(json.dumps(summaries, default=lambda x: x.tolist()), flush=True)


if __name__ == "__main__":
    run()
