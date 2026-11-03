"""Causal/following TLE diagnosis; phase estimated only from curved fragments."""

import hashlib
import json

import matplotlib
import numpy as np
from analyze_dsx01_fixed_site import ecef_states
from associate_merged_track_catalogue import write
from dsx01_cut_linear import curve_posterior
from probe_dsx01_cut_linear import prepare
from probe_dsx01_scan_influence import OUTPUT as HISTORY
from report_dsx01_joint_marginal import reference_xy
from run_dsx01_causal_correlation import OUTPUT
from sgp4.api import Satrec

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD, profile
from leo.sky.propagation import ElementSetCatalogue

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def phase_search(score):
    grid = np.linspace(-15.0, 15.0, 61)
    values = np.array([score(phase) for phase in grid])
    x, value = float(grid[np.argmin(values)]), float(values.min())
    for _ in range(12):
        h = 0.01
        plus, minus = score(min(15.0, x + h)), score(max(-15.0, x - h))
        gradient = (plus - minus) / (2 * h)
        curvature = (plus + minus - 2 * value) / h**2
        step = float(np.clip(-gradient / max(0.01, curvature), -1.0, 1.0))
        if abs(step) < 1e-5:
            break
        found = False
        for fraction in 2.0 ** -np.arange(10):
            trial = float(np.clip(x + fraction * step, -15, 15))
            cost = score(trial)
            if cost < value:
                x, value, found = trial, float(cost), True
                break
        if not found:
            break
    return x, value


def run():
    case, norad = "DSX01-S05", 63387
    scan, fits, problems, nominations, _ = prepare(case)
    p = problems["c0"]
    target = int(np.flatnonzero(scan.norads == norad)[0])
    chosen = [
        (i, a)
        for i, row, a in zip(p.members, p.rows, p.alias, strict=True)
        if row["candidate_index"] == target
    ]
    linear = [
        (r["index"], r["alias"]) for r in nominations if r["accepted"] and r.get("norad") == norad
    ]
    history_path = HISTORY / "orbit_history_and_following_diagnostic.json"
    history = json.loads(history_path.read_text())[case]["candidates"][str(norad)]
    following = history["first_following_newer_version"]
    if following is None or following["collected_utc_ns"] <= scan.receipt["origin_utc_ns"]:
        raise ValueError("a strictly following publication is required for this diagnostic")
    versions = {
        name: row["lines"]
        for name, row in [("causal", history["latest_causal"]), ("following", following)]
    }
    skies = {}
    for name, lines in versions.items():
        catalogue = ElementSetCatalogue((str(norad),), (norad,), (Satrec.twoline2rv(*lines),))
        position, velocity, good = ecef_states(
            catalogue, scan.receipt["origin_utc_ns"], scan.sky["time_s"]
        )
        if not good.all():
            raise ValueError("SGP4 diagnostic propagation failed")
        skies[name] = dict(time_s=scan.sky["time_s"], position_km=position, velocity_km_s=velocity)
    directory = OUTPUT / "late_family"
    directory.mkdir(parents=True, exist_ok=True)
    rows, partial, phases = [], [], []
    residuals = {}
    for label, x in [
        ("blind", np.asarray(fits["c0"]["parameters"])),
        ("evaluation_GPS", reference_xy()),
    ]:
        state = p.state(x)
        posterior, _ = curve_posterior(p, x)
        lat = 37.906 + x[1] / 111.0
        lon = -122.545 + x[0] / (111.32 * np.cos(np.deg2rad(37.906)))
        for i, row, sl in zip(p.members, p.rows, p.slices, strict=True):
            track = scan.tracks[i]
            use = (track["times"] >= 279) & (track["times"] <= 294.2)
            if use.sum() < 6 or np.ptp(track["times"][use]) < 6:
                continue
            t = track["times"][use]
            r = posterior["conditional_residual_hz"][sl][use]
            dt = t - t.mean()
            partial.append(
                dict(
                    position=label,
                    component=track["key"],
                    norad=row["candidate_norad"],
                    receiver=track["receiver"],
                    channel=track["channel"],
                    points=len(t),
                    start_s=float(t.min()),
                    end_s=float(t.max()),
                    slope_hz_s=float(dt @ r / (dt @ dt)),
                    rms_centered_hz=float(np.std(r)),
                )
            )

        def terms(i, alias, sky, phase, state=state, lat=lat, lon=lon):
            track = scan.tracks[i]
            t = track["times"]
            q = track["rf_hz"] / 11.5e9
            radio = (
                scan.hardware(track, state["beta"])
                + q * scan.rx_basis[i] @ state["smooth"][track["receiver"] - 1]
            )
            frequency, _ = paired_phase_frequency(
                sky, t, np.zeros(len(t), int), np.array([phase]), lat, lon
            )
            return profile(
                track["values"] + alias * PERIOD - radio, q * frequency, scan.white[i][0]
            )

        for version, sky in skies.items():
            sigma = max(1.0, float(scan.sky["phase_sigma_s"][target]))

            def objective(phase, sky=sky, sigma=sigma):
                return phase**2 / sigma**2 + sum(
                    terms(i, alias, sky, phase)["cost"][0] for i, alias in chosen
                )

            phase, cost = phase_search(objective)
            phases.append(
                dict(
                    position=label,
                    version=version,
                    phase_s=phase,
                    score=cost,
                    phase_sigma_s=sigma,
                    curved_points=sum(len(scan.tracks[i]["times"]) for i, _ in chosen),
                )
            )
            for kind, population in [("curved", chosen), ("linear", linear)]:
                for i, alias in population:
                    track = scan.tracks[i]
                    term = terms(i, alias, sky, phase)
                    r = term["residual"][0]
                    t = track["times"]
                    dt = t - t.mean()
                    row = dict(
                        position=label,
                        version=version,
                        kind=kind,
                        component=track["key"],
                        receiver=track["receiver"],
                        channel=track["channel"],
                        points=len(t),
                        rms_hz=float(term["rms"][0]),
                        bias_hz=float(term["bias"][0]),
                        slope_hz_s=float(dt @ r / (dt @ dt)),
                        extra_alias=int(term["alias"][0]),
                    )
                    rows.append(row)
                    residuals[(label, version, track["key"])] = dict(times=t, residual=r)
    write(
        directory / "diagnostic.json",
        dict(
            hypothesis=(
                "Only phase and independent constants; "
                "radio calibration held to normal curved-only posterior"
            ),
            no_linear_phase_or_calibration_fit=True,
            future_TLE_postfit_diagnostic_only=True,
            evaluation_GPS_only_in_postfit_diagnostic=True,
            same_curved_observations_150Hz_noise_phase_prior_and_search_budgets=True,
            historical_elements=history,
            history_sha256=hashlib.sha256(history_path.read_bytes()).hexdigest(),
            phase_fits=phases,
            fragment_results=rows,
            unrelated_late_curved_comparison=partial,
        ),
    )
    write(directory / "residuals.json", {"/".join(key): value for key, value in residuals.items()})
    fig, axes = plt.subplots(2, 2, figsize=(15, 8), sharex=True, sharey=True)
    for ax, (label, version) in zip(
        axes.ravel(),
        [(a, b) for a in ["blind", "evaluation_GPS"] for b in ["causal", "following"]],
        strict=True,
    ):
        for row in [r for r in rows if r["position"] == label and r["version"] == version]:
            item = residuals[(label, version, row["component"])]
            if row["kind"] == "curved":
                ax.plot(item["times"], item["residual"], ".-", alpha=0.7, label=row["component"])
            elif row["receiver"] == 2:
                ax.plot(item["times"], item["residual"], "x--", alpha=0.65, label=row["component"])
        ax.axhline(0, color="black", linewidth=0.7)
        ax.set_title(label + " / " + version)
        ax.set_xlim(220, 300)
        ax.set_ylim(-900, 900)
        ax.set_ylabel("Residual after fragment constant (Hz)")
        ax.set_xlabel("Time into scan (seconds)")
    axes[0, 1].legend(fontsize=6, ncol=2)
    fig.tight_layout()
    fig.savefig(directory / "63387_phase_transfer.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(json.dumps(dict(phase_fits=phases, unrelated_late_curved_comparison=partial)), flush=True)


if __name__ == "__main__":
    run()
