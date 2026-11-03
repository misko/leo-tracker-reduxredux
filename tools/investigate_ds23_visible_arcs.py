"""Local, reproducible radio-arc diagnostics; no future TLE or GPS selection."""

import argparse
import json
from itertools import combinations
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from associate_merged_track_catalogue import write

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/2026_10_18_ds23_phase_refreshed_evaluation"
OUT = ROOT / "reports/2026_10_18_ds23_visible_arcs"
PERIOD = 1 / 4.4e-6


def read(path):
    return json.loads(path.read_text())


def spline_design(times, degree, knots, lo, hi):
    """C1 spline with degree <=4; repeated internal knots permit curvature changes."""
    t = np.asarray(times, float)
    x = (t - lo) / (hi - lo)
    columns = [x**j for j in range(degree + 1)]
    columns.extend(
        np.maximum(x - (k - lo) / (hi - lo), 0) ** j for k in knots for j in range(2, degree + 1)
    )
    return np.array(columns).T


def polynomial_models(t, y, sigma):
    """Compare fixed-support fits, charging coefficients and searched breakpoints."""
    t, y = np.asarray(t), np.asarray(y)
    rows = []
    for degree in range(1, 5):
        design = spline_design(t, degree, [], t.min(), t.max())
        residual = y - design @ np.linalg.lstsq(design, y, rcond=None)[0]
        rows.append(
            dict(degree=degree, knots=[], coefficients=design.shape[1], residual_hz=residual)
        )
    grid = np.arange(np.ceil((t.min() + 10) / 5) * 5, t.max() - 10, 5.0)
    for degree in (2, 3, 4):
        for count in (1, 2):
            for knots in combinations(grid, count):
                edges = np.r_[t.min(), knots, t.max() + 1e-6]
                counts = np.histogram(t, edges)[0]
                if min(counts) < max(8, 4 * (degree + 1)):
                    continue
                design = spline_design(t, degree, knots, t.min(), t.max())
                residual = y - design @ np.linalg.lstsq(design, y, rcond=None)[0]
                rows.append(
                    dict(
                        degree=degree,
                        knots=knots,
                        coefficients=design.shape[1],
                        residual_hz=residual,
                    )
                )
    for row in rows:
        r = row["residual_hz"]
        row.update(
            rms_hz=float(np.sqrt(np.mean(r * r))),
            maximum_hz=float(max(abs(r))),
            bic=float(
                np.sum((r / sigma) ** 2)
                + (row["coefficients"] + len(row["knots"])) * np.log(len(t))
            ),
            diagnostics={k: v[0] for k, v in batch_noise_screen(r[None], t).items()},
        )
    return sorted(rows, key=lambda r: r["bic"])


def radio(case, channel, lo, hi):
    OUT.mkdir(exist_ok=True)
    obs = [
        o
        for o in read(SOURCE / case / "observations.json")
        if o["receiver"] == 1 and o["channel"] == channel
    ]
    tracks = [
        t
        for t in read(SOURCE / case / "tracks.json")
        if t["receiver"] == 1 and t["channel"] == channel
    ]
    owner = {
        oid: t["key"].split("-T")[-1].split("-RF")[0]
        for t in tracks
        for oid in t["observation_ids"]
    }
    selected = [o for o in obs if lo <= o["time_s"] <= hi]
    t = np.array([o["time_s"] for o in selected])
    y = np.array([o["measured_cfo_hz"] for o in selected])
    sigma = read(SOURCE / case / "radio_noise.json")["constant_radio_sigma_hz"]
    models = polynomial_models(t, y, sigma)
    write(
        OUT / f"{case}_radio.json",
        dict(
            case=case,
            observations=selected,
            owners=[owner.get(o["observation_id"]) for o in selected],
            sigma_hz=sigma,
            models=models,
            GPS_or_satellites_used=False,
        ),
    )
    fig, axes = plt.subplots(3, 1, figsize=(13, 11), sharex=True)
    for label in sorted(set(owner.values())):
        mask = np.array([owner.get(o["observation_id"]) == label for o in selected])
        if mask.any():
            axes[0].scatter(t[mask], y[mask] / 1000, s=22, label=f"T{label}")
    missing = np.array([o["observation_id"] not in owner for o in selected])
    axes[0].scatter(
        t[missing],
        y[missing] / 1000,
        s=26,
        c="black",
        marker="x",
        label=f"Untracked ({missing.sum()})",
    )
    axes[0].set(ylabel="Raw GLRT CFO (kHz)", title=f"{case} RX1 CH{channel}: graph ownership")
    axes[0].legend(ncol=5)
    for row, color in [
        (next(m for m in models if m["degree"] == 4 and not m["knots"]), "tab:red"),
        (models[0], "tab:blue"),
    ]:
        label = (
            f"degree {row['degree']}; knots {[float(k) for k in row['knots']]}; "
            f"RMS {row['rms_hz']:.1f} Hz"
        )
        axes[1].plot(t, row["residual_hz"], ".-", c=color, label=label)
    axes[1].axhline(0, c=".4", lw=0.8)
    axes[1].set(ylabel="Polynomial residual (Hz)")
    axes[1].legend(fontsize=9)
    dt = np.diff(t)
    axes[2].plot((t[1:] + t[:-1]) / 2, np.diff(y) / dt, ".-", color=".4")
    axes[2].set(
        xlabel="Time since scan start (s)", ylabel="Adjacent-point slope (Hz/s)", ylim=(-9000, 3000)
    )
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / f"{case}_radio.png", dpi=160)
    plt.close(fig)
    print(
        case,
        len(t),
        "untracked",
        int(missing.sum()),
        [(m["degree"], m["knots"], round(m["rms_hz"], 2), round(m["bic"], 2)) for m in models[:4]],
        flush=True,
    )


def frozen(case, arm):
    """Leave target graph tracks out of calibration, preserving original design."""
    import investigate_ds23_adaptive_failures as previous
    from investigate_dsx01_localization_failures import DiagnosticNormal

    cache = OUT / f"{case}_{arm}_frozen.json"
    if cache.exists():
        return read(cache)
    previous.USE_GENUINE_PRIOR = True
    scan, _, winner = previous.context(case)
    base = DiagnosticNormal(scan, winner["node"], scan.radio_sigma_hz, arm == "fitted_c")
    keep = np.ones(len(base.values), bool)
    for row, sl in zip(base.rows, base.slices, strict=True):
        if (
            "RX1-CH2-T002" in row["component"]
            if case == "DS23-0342"
            else "RX1-CH1-T000" in row["component"] or "RX1-CH1-T002" in row["component"]
        ):
            keep[sl] = False
    p, fit, history, widths = previous.repaired_fit(scan, winner["node"], arm, "causal", keep)
    state = p.state(fit["parameters"])
    result = dict(
        endpoint=fit["parameters"],
        state=state,
        fit=fit,
        phase_changes=history,
        prior_receipt=widths,
        target_excluded_from_calibration=True,
        GPS_used=False,
    )
    write(cache, result)
    return result


def exact_orbit_frequency(lines, origin, times, lat, lon, rf, parameters):
    """Actual SGP4; element increments pivot phase at scan start to reduce covariance."""
    from analyze_dsx01_fixed_site import ecef_states
    from sgp4.api import WGS72, Satrec

    from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
    from leo.sky.frames import geodetic_to_ecef_km, julian_day_from_utc_ns
    from leo.sky.propagation import ElementSetCatalogue

    phase, dn, di, draan, dex, dey = parameters[:6]
    base = Satrec.twoline2rv(*lines)
    ex, ey = base.ecco * np.cos(base.argpo) + dex, base.ecco * np.sin(base.argpo) + dey
    eccentricity, omega = float(np.hypot(ex, ey)), float(np.arctan2(ey, ex) % (2 * np.pi))
    jd, fr = julian_day_from_utc_ns(np.array([origin]))
    elapsed_min = float((jd[0] - base.jdsatepoch + fr[0] - base.jdsatepochF) * 1440)
    delta_n = dn * 2 * np.pi / 1440
    mean = (base.mo + base.argpo - omega - delta_n * elapsed_min) % (2 * np.pi)
    sat = Satrec()
    sat.sgp4init(
        WGS72,
        base.operationmode,
        base.satnum,
        base.jdsatepoch - 2433281.5 + base.jdsatepochF,
        base.bstar,
        base.ndot,
        base.nddot,
        eccentricity,
        omega,
        base.inclo + np.deg2rad(di),
        mean,
        base.no_kozai + delta_n,
        base.nodeo + np.deg2rad(draan),
    )
    sat.jdsatepoch, sat.jdsatepochF = base.jdsatepoch, base.jdsatepochF
    catalogue = ElementSetCatalogue(("candidate",), (base.satnum,), (sat,))
    position, velocity, usable = ecef_states(catalogue, origin, times + phase)
    if not usable.all():
        raise ValueError("unusable perturbed orbit")
    angle = EARTH_ROTATION_RAD_S * phase
    for a in (position, velocity):
        x, y = a[..., 0].copy(), a[..., 1].copy()
        a[..., 0], a[..., 1] = (
            np.cos(angle) * x - np.sin(angle) * y,
            np.sin(angle) * x + np.cos(angle) * y,
        )
    relative = position[0] - geodetic_to_ecef_km(lat, lon, 0)
    return (
        -rf / 299792.458 * np.sum(relative * velocity[0], axis=1) / np.linalg.norm(relative, axis=1)
    )


def orbital(case, arm):
    from evaluate_ds23_phase_refreshed import FreshScan
    from prototype_dsx01_continuous_position import latlon

    from leo.analysis.research.retained_track_likelihood import projected_receiver_basis

    frozen_fit = frozen(case, arm)
    scan = FreshScan(SOURCE / case, noise_mode="radio")
    channel, lo, hi = (2, 73.5, 133.5) if case == "DS23-0342" else (1, 134.0, 240.0)
    obs = [
        o
        for o in read(SOURCE / case / "observations.json")
        if o["receiver"] == 1 and o["channel"] == channel and lo <= o["time_s"] <= hi
    ]
    if case == "DS23-0342":
        # All visible marks except the isolated 114-second competing peak.
        # Also evaluate the exact published support separately, below.
        obs = [o for o in obs if not 113 < o["time_s"] < 115]
    t = np.array([o["time_s"] for o in obs])
    raw = np.array([o["measured_cfo_hz"] for o in obs])
    rf = obs[0]["actual_rf_hz"]
    dummy = dict(receiver=1, channel=channel, times=t, rf_hz=rf, bank="CH1-4")
    state = frozen_fit["state"]
    radio = scan.hardware(dummy, np.array(state["beta"]))
    radio += rf / 11.5e9 * projected_receiver_basis(t) @ np.array(state["smooth"])[0]
    y = raw - radio
    nominal = read(SOURCE / case / "nominal_elements.json")
    origin = scan.receipt["origin_utc_ns"]
    lat, lon = latlon(frozen_fit["endpoint"])
    sigma = scan.radio_sigma_hz
    candidates = [68214, 68004, 45096, 65504] if case == "DS23-0342" else [59569]
    scales = np.array([3.0, 0.002, 0.02, 0.02, 0.0001, 0.0001, 1000.0, 0.5, 0.005])
    bounds = np.array([15.0, 0.2, 1.0, 1.0, 0.01, 0.01, 100000.0, 50.0, 0.2]) / scales
    results = []
    for norad in candidates:
        entry = nominal[str(norad)]
        lines = entry.get("lines", entry.get("tle_lines"))
        if lines is None:
            lines = [entry["line1"], entry["line2"]]
        for mode, active, prior in [
            ("phase_bias", [0, 6], True),
            ("phase_bias_drift", [0, 6, 7], True),
            ("phase_bias_scale", [0, 6, 8], True),
            ("orbit_prior", list(range(7)), True),
            ("orbit_free", list(range(7)), False),
            ("orbit_drift_scale", list(range(9)), False),
        ]:
            best = None
            for phase in (-6.0, 0.0, 6.0):
                u0 = np.zeros(9)
                u0[0] = phase / scales[0]
                initial = exact_orbit_frequency(lines, origin, t, lat, lon, rf, u0 * scales)
                alias = int(np.rint(np.median(initial - y) / PERIOD))
                target = y + alias * PERIOD
                u0[6] = np.mean(target - initial) / scales[6]

                def residual(z, active=active, lines=lines, target=target, prior=prior):
                    u = np.zeros(9)
                    u[active] = z
                    a = u * scales
                    prediction = exact_orbit_frequency(lines, origin, t, lat, lon, rf, a)
                    prediction = prediction * (1 + a[8]) + a[6] + a[7] * (t - t.mean())
                    r = (target - prediction) / sigma
                    return np.r_[r, z] if prior else r

                fitted = bounded_gauss_newton(
                    residual, u0[active], -bounds[active], bounds[active], iterations=70, step=1e-3
                )
                u = np.zeros(9)
                u[active] = fitted["parameters"]
                a = u * scales
                rr = residual(fitted["parameters"])
                r = rr[: len(t)] * sigma
                result = dict(
                    norad=norad,
                    mode=mode,
                    parameters=a,
                    alias=alias,
                    parameter_names=[
                        "phase_s",
                        "dn_rev_day",
                        "di_deg",
                        "dRAAN_deg",
                        "d_e_cos",
                        "d_e_sin",
                        "bias_hz",
                        "drift_hz_s",
                        "doppler_scale_delta",
                    ],
                    rms_hz=float(np.sqrt(np.mean(r * r))),
                    residual_hz=r,
                    score=float(np.sum(rr**2)),
                    evaluations=fitted["evaluations"],
                    diagnostics={k: v[0] for k, v in batch_noise_screen(r[None], t).items()},
                    prior_enabled=prior,
                    prior_scales=scales,
                    stopped=fitted["stopped"],
                )
                if best is None or result["score"] < best["score"]:
                    best = result
            results.append(best)
            write(
                OUT / f"{case}_{arm}_orbits.json",
                dict(
                    case=case,
                    arm=arm,
                    times=t,
                    raw_cfo_hz=raw,
                    calibrated_cfo_hz=y,
                    radio_hz=radio,
                    sigma_hz=sigma,
                    observation_ids=[o["observation_id"] for o in obs],
                    results=results,
                    GPS_used=False,
                    future_TLE_used=False,
                    calibration_endpoint=frozen_fit["endpoint"],
                    explicit_competing_point_exclusion_s=[113, 115]
                    if case == "DS23-0342"
                    else None,
                ),
            )
            print(
                case,
                arm,
                norad,
                mode,
                round(best["rms_hz"], 2),
                best["diagnostics"]["noise_screen_pass"],
                flush=True,
            )
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
    axes[0].scatter(t, raw / 1000, c="black", s=14, label="GLRT measurements")
    for row in results:
        if row["norad"] != candidates[0]:
            continue
        prediction = raw - np.array(row["residual_hz"])
        axes[0].plot(t, prediction / 1000, label=f"{row['mode']}: {row['rms_hz']:.0f} Hz RMS")
        axes[1].plot(t, row["residual_hz"], ".-", label=row["mode"])
    axes[0].set(
        title=f"{case} RX1 CH{channel}: exact SGP4 single-satellite tests ({arm})",
        ylabel="Raw CFO (kHz)",
    )
    axes[1].set(xlabel="Time (s)", ylabel="Residual (Hz)")
    for ax in axes:
        ax.legend(fontsize=9)
        ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / f"{case}_{arm}_orbits.png", dpi=160)
    plt.close(fig)


def transition(arm):
    """Cross-channel support and independent candidate peaks around the S342 join."""
    from evaluate_ds23_phase_refreshed import FreshScan
    from prototype_dsx01_continuous_position import latlon

    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
    from leo.analysis.research.retained_track_likelihood import profile, projected_receiver_basis

    case = "DS23-0342"
    scan = FreshScan(SOURCE / case, noise_mode="radio")
    frozen_fit = frozen(case, arm)
    state = frozen_fit["state"]
    obs = [
        o
        for o in read(SOURCE / case / "observations.json")
        if o["receiver"] == 1
        and o["channel"] == 2
        and 65 <= o["time_s"] <= 134
        and not 113 < o["time_s"] < 115
    ]
    t = np.array([o["time_s"] for o in obs])
    raw = np.array([o["measured_cfo_hz"] for o in obs])
    q = obs[0]["actual_rf_hz"] / 11.5e9
    dummy = dict(receiver=1, channel=2, times=t, rf_hz=q * 11.5e9, bank="CH1-4")
    radio_hz = scan.hardware(dummy, np.array(state["beta"]))
    radio_hz += q * projected_receiver_basis(t) @ np.array(state["smooth"])[0]
    y = raw - radio_hz
    rows = []
    for norad, mask in [(65504, t < 86), (68214, t > 89)]:
        j = int(np.flatnonzero(scan.norads == norad)[0])
        grid = np.linspace(-15, 15, 121)
        bank = dict(
            time_s=scan.sky["time_s"],
            position_km=np.repeat(scan.sky["position_km"][[j]], len(grid), axis=0),
            velocity_km_s=np.repeat(scan.sky["velocity_km_s"][[j]], len(grid), axis=0),
        )
        f, _ = paired_phase_frequency(
            bank,
            np.tile(t, len(grid)),
            np.repeat(np.arange(len(grid)), len(t)),
            grid,
            *latlon(frozen_fit["endpoint"]),
        )
        predictions = q * f.reshape(len(grid), -1)
        terms = profile(
            y[mask], predictions[:, mask], np.eye(int(mask.sum())) / scan.radio_sigma_hz
        )
        b = int(np.argmin(terms["cost"] + grid**2 / 9))
        shared = float(state["phases"][j])
        s = int(np.argmin(abs(grid - shared)))
        variants = [("local_phase", b)]
        if norad == 65504:
            variants.append(("independent_family_phase", s))
        for phase_type, k in variants:
            residual = terms["residual"][k]
            rows.append(
                dict(
                    norad=norad,
                    phase_type=phase_type,
                    points=int(mask.sum()),
                    phase_s=float(grid[k]),
                    independent_phase_s=shared,
                    rms_hz=float(terms["rms"][k]),
                    bias_hz=float(terms["bias"][k]),
                    diagnostics={
                        a: v[0] for a, v in batch_noise_screen(residual[None], t[mask]).items()
                    },
                    residual_hz=residual,
                    times=t[mask],
                    prediction_all_hz=predictions[k]
                    + terms["bias"][k]
                    + radio_hz
                    - terms["alias"][k] * PERIOD,
                )
            )
    # One published graph support versus the omitted marks: no fitting selection here.
    target = next(a for a in scan.tracks if "RX1-CH2-T002" in a["key"])
    original = set(target["observation_ids"])
    grid_models = polynomial_models(t, raw, scan.radio_sigma_hz)
    # Candidate peaks remain separate from winning marks; no assertion that every
    # peak is a separate emitter. Show all gated peaks modulo the same alias branch.
    document = read(SOURCE / case / "tracking.json")
    anchor = document["timing"]["session_start_device_sample_counter"]
    samples = document["sample_rate_hz"]
    raw_peaks = []
    for probe in document["probes"]:
        if probe["receiver_id"] != 0 or probe["channel"] != 2:
            continue
        time_s = (probe["valid_start_counter"] - anchor) / samples + document["probe_ms"] / 2000
        if not 60 <= time_s <= 140:
            continue
        for c in probe["candidates"]:
            raw_peaks.append(
                dict(
                    time_s=time_s,
                    cfo_hz=c["fractional_tracking_cfo_hz"],
                    margin=c["fractional_margin"],
                    passed=c["passed_fractional_margin_gate"],
                )
            )
    write(
        OUT / f"{case}_{arm}_transition.json",
        dict(
            case=case,
            arm=arm,
            times=t,
            raw_cfo_hz=raw,
            rows=rows,
            polynomial_models=grid_models,
            original_graph_mask=[o["observation_id"] in original for o in obs],
            all_candidate_peaks=raw_peaks,
            GPS_used=False,
            future_TLE_used=False,
            note="Transition split is a targeted diagnostic, not an automatic classifier.",
        ),
    )
    fig, axes = plt.subplots(3, 1, figsize=(13, 11), sharex=True)
    baseline = -510000 - 3300 * (t - 74)
    axes[0].scatter(t, (raw - baseline) / 1000, c="black", s=20, label="Winning GLRT marks")
    for row in rows:
        if row["phase_type"] != "local_phase":
            continue
        predicted = np.array(row["prediction_all_hz"])
        axes[0].plot(t, (predicted - baseline) / 1000, label=f"NORAD {row['norad']}")
        axes[1].plot(
            row["times"],
            row["residual_hz"],
            ".-",
            label=f"{row['norad']}: {row['points']} points, RMS {row['rms_hz']:.0f} Hz",
        )
    for row in grid_models[:1]:
        axes[2].plot(
            t,
            row["residual_hz"],
            ".-",
            label=f"C1 polynomial: degree {row['degree']}; "
            f"knots {[float(k) for k in row['knots']]} "
            f"RMS {row['rms_hz']:.0f} Hz",
        )
    axes[0].set(
        title=f"{case} RX1 CH2: extended prefix and suffix ({arm})",
        ylabel="CFO minus common line (kHz)",
    )
    axes[1].set(ylabel="Satellite residual (Hz)")
    axes[2].set(ylabel="Radio polynomial residual (Hz)", xlabel="Time (s)")
    for ax in axes:
        ax.axvspan(85.9, 89.4, color=".8", alpha=0.4)
        ax.grid(alpha=0.2)
        ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / f"{case}_{arm}_transition.png", dpi=160)
    plt.close(fig)
    for row in rows:
        print(
            arm,
            row["norad"],
            row["phase_type"],
            row["points"],
            row["rms_hz"],
            row["bias_hz"],
            row["diagnostics"],
            flush=True,
        )


def peak_overlap(arm):
    """Test continuation peaks against predictions fitted before those peaks."""
    a = read(OUT / f"DS23-0342_{arm}_transition.json")
    t = np.array(a["times"])
    rows = [r for r in a["rows"] if r["phase_type"] == "local_phase"]
    support = {r["norad"]: [] for r in rows}
    simultaneous = []
    peaks = a["all_candidate_peaks"]
    for time in sorted(
        {p["time_s"] for p in peaks if p["passed"] and t[0] <= p["time_s"] <= t[-1]}
    ):
        eligible = [p for p in peaks if p["time_s"] == time and p["passed"]]
        predictions = [float(np.interp(time, t, r["prediction_all_hz"])) for r in rows]
        found = []
        for row, prediction in zip(rows, predictions, strict=True):
            candidates = []
            for peak in eligible:
                residual = (peak["cfo_hz"] - prediction + PERIOD / 2) % PERIOD - PERIOD / 2
                if abs(residual) <= 600:
                    candidates.append(
                        dict(peak, residual_hz=float(residual), lifted_cfo_hz=prediction + residual)
                    )
            if candidates:
                selected = min(candidates, key=lambda p: abs(p["residual_hz"]))
                support[row["norad"]].append(selected)
                found.append(row["norad"])
        if len(found) == 2 and abs(predictions[0] - predictions[1]) > 1500:
            simultaneous.append(
                dict(time_s=time, separation_hz=abs(predictions[0] - predictions[1]))
            )
    summaries = {}
    for norad, points in support.items():
        holdout = [p for p in points if 89 <= p["time_s"] <= 117.7]
        r = np.array([p["residual_hz"] for p in holdout])
        summaries[norad] = dict(
            heldout_points=len(holdout),
            rms_hz=float(np.sqrt(np.mean(r * r))) if len(r) else None,
            mean_hz=float(r.mean()) if len(r) else None,
        )
    # Include actual simultaneous examples, rather than mistaking duplicate or
    # +/-P replicas of one GLRT peak for two satellites.
    examples = []
    for item in simultaneous:
        time = item["time_s"]
        matching = [(n, next(p for p in support[n] if p["time_s"] == time)) for n in support]
        if 100 < time < 110:
            examples.append(dict(time_s=time, peaks=[dict(norad=n, **p) for n, p in matching]))
    write(
        OUT / f"DS23-0342_{arm}_peak_overlap.json",
        dict(
            support=support,
            simultaneous=simultaneous,
            simultaneous_examples=examples,
            continuation_summary=summaries,
            continuation_peaks_not_used_to_fit_prefix_prediction=True,
            candidate_window_hz=600,
            caveat="Gated-nearest prediction support is conditional, not unbiased noise.",
        ),
    )
    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    for row, color in zip(rows, ["tab:blue", "tab:orange"], strict=True):
        norad = row["norad"]
        pred = np.array(row["prediction_all_hz"])
        baseline = -510000 - 3300 * (t - 74)
        axes[0].plot(t, (pred - baseline) / 1000, c=color, label=f"NORAD {norad} prediction")
        points = support[norad]
        tt = np.array([p["time_s"] for p in points])
        yy = np.array([p["lifted_cfo_hz"] for p in points])
        axes[0].scatter(
            tt,
            (yy - (-510000 - 3300 * (tt - 74))) / 1000,
            c=color,
            s=24,
            label=f"{norad}: gated candidate peaks",
        )
        axes[1].scatter(
            tt,
            [p["residual_hz"] for p in points],
            c=color,
            s=20,
            label=f"{norad}: candidate minus prediction",
        )
    raw = np.array(a["raw_cfo_hz"])
    axes[0].scatter(
        t,
        (raw - (-510000 - 3300 * (t - 74))) / 1000,
        s=75,
        facecolors="none",
        edgecolors="black",
        label="Winner used by original graph",
    )
    axes[0].axvspan(89, 117.7, color=".8", alpha=0.25)
    axes[0].set(
        title="DS23-0342 RX1 CH2: both curves exist in the same probes",
        ylabel="CFO minus common line (kHz)",
    )
    axes[1].set(xlabel="Time (s)", ylabel="Candidate residual (Hz)")
    for ax in axes:
        ax.grid(alpha=0.2)
        ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / f"DS23-0342_{arm}_peak_overlap.png", dpi=160)
    plt.close(fig)
    print("simultaneous probes", len(simultaneous), "continuation", summaries, flush=True)


def combined_figures():
    """Readable comparison: original ownership, repaired curve, physical orbit."""
    case = "DS23-0039"
    radio_fit = read(OUT / f"{case}_radio.json")
    trace = read(OUT / f"{case}_graph_trace.json")
    repair = max(trace["prototype_repairs"], key=lambda r: len(r["indices"]))
    t = np.array(repair["times"])
    raw = np.array([o["measured_cfo_hz"] for o in radio_fit["observations"]])
    physical = read(OUT / f"{case}_c0_orbits.json")
    orbit = next(r for r in physical["results"] if r["mode"] == "orbit_prior")
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True)
    for label, color in [
        ("000", "tab:blue"),
        ("001", "tab:orange"),
        ("002", "tab:green"),
        (None, "black"),
    ]:
        mask = np.array([o == label for o in radio_fit["owners"]])
        axes[0].scatter(
            t[mask],
            raw[mask] / 1000,
            c=color,
            s=22,
            marker="x" if label is None else "o",
            label="Untracked" if label is None else f"T{label}",
        )
    residual = np.array(repair["model"]["residual_hz"])
    axes[1].scatter(t, raw / 1000, s=18, c="tab:purple", label="All 88 GLRT points in one track")
    axes[1].plot(
        t,
        (raw - np.array(orbit["residual_hz"])) / 1000,
        c="black",
        lw=1.3,
        label="59569: causal SGP4 + constrained physical correction",
    )
    axes[1].axvline(repair["model"]["knots"][0], ls=":", c=".5", label="C1 polynomial knot")
    axes[2].plot(
        t, residual, ".-", label=f"Polynomial residual: {repair['model']['rms_hz']:.1f} Hz RMS"
    )
    axes[2].plot(
        t,
        orbit["residual_hz"],
        ".-",
        alpha=0.65,
        label=f"SGP4 residual: {orbit['rms_hz']:.1f} Hz RMS",
    )
    axes[0].set(
        title="DS23-0039 RX1 CH1: graph path existed, polynomial finalization fragmented it",
        ylabel="Original CFO (kHz)",
    )
    axes[1].set(ylabel="Repaired CFO (kHz)")
    axes[2].set(ylabel="Residual (Hz)", xlabel="Time since scan start (s)")
    for ax in axes:
        ax.grid(alpha=0.2)
        ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / f"{case}_repair.png", dpi=160)
    plt.close(fig)


def repair_path(t, y, path, lifted, sigma=150.0):
    """Prototype: preserve a discovered graph path using penalized C1 pieces.

    Search the original path before point clipping, then grow from its model.
    No satellite IDs or position enter this radio-only operation.
    """
    t, y = np.asarray(t), np.asarray(y)
    ix = np.asarray(path, int)
    target = np.asarray(lifted, float)
    for _ in range(3):
        models = polynomial_models(t[ix], target, sigma)
        accepted = [
            r
            for r in models
            if r["maximum_hz"] < 3 * sigma and r["diagnostics"]["noise_screen_pass"]
        ]
        if not accepted:
            return None
        best = accepted[0]
        design = spline_design(t[ix], best["degree"], best["knots"], t[ix].min(), t[ix].max())
        coeff = np.linalg.lstsq(design, target, rcond=None)[0]
        available = np.flatnonzero((t >= t[ix].min()) & (t <= t[ix].max()))
        prediction = (
            spline_design(t[available], best["degree"], best["knots"], t[ix].min(), t[ix].max())
            @ coeff
        )
        residual = (y[available] - prediction + PERIOD / 2) % PERIOD - PERIOD / 2
        new = available[abs(residual) < 3 * sigma]
        new_target = (prediction + residual)[abs(residual) < 3 * sigma]
        if np.array_equal(ix, new):
            return dict(
                indices=ix,
                times=t[ix],
                values=target,
                model=best,
                coefficients=coeff,
                max_observed_gap_s=float(np.max(np.diff(t[ix]))),
            )
        ix, target = new, new_target
    return None


def graph_trace():
    """Instrument the unchanged graph code to locate discovery/support loss."""
    from leo.analysis import graph_tracklets as graph
    from leo.analysis.polynomial_tracklets import TrackConfig, _predict

    case = "DS23-0039"
    obs = [
        o
        for o in read(SOURCE / case / "observations.json")
        if o["receiver"] == 1 and o["channel"] == 1
    ]
    t = np.array([o["time_s"] for o in obs])
    y = np.array([o["measured_cfo_hz"] for o in obs])
    config = TrackConfig(
        **read(ROOT / "reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json")["config"]
    )
    traces = []
    original = graph._path_models

    def traced(tt, yy, path, lifted, available, cfg, depth=0):
        result = original(tt, yy, path, lifted, available, cfg, depth)
        traces.append(
            dict(
                depth=depth,
                path_times=tt[path],
                path_indices=path,
                lifted=lifted,
                input_points=len(path),
                model_supports=[tt[m["indices"]] for m in result],
            )
        )
        return result

    graph._path_models = traced
    try:
        result = graph.fit_lane(t, y, config)
    finally:
        graph._path_models = original
    # Automatically pick graph pieces that coexist at the same frequency over
    # >=6s; this records evidence for a union repair, without satellite/GPS input.
    overlapping = []
    for a, b in combinations(result["tracks"], 2):
        pa, pb = a["pieces"][0], b["pieces"][0]
        lo = max(t[a["indices"]].min(), t[b["indices"]].min())
        hi = min(t[a["indices"]].max(), t[b["indices"]].max())
        if hi - lo < 6:
            continue
        sample = np.linspace(lo, hi, 11)
        difference = (
            _predict(pa, sample) - _predict(pb, sample) + PERIOD / 2
        ) % PERIOD - PERIOD / 2
        if np.median(abs(difference)) < 450:
            overlapping.append(
                dict(
                    left_times=t[a["indices"]],
                    right_times=t[b["indices"]],
                    median_disagreement_hz=float(np.median(abs(difference))),
                )
            )
    repairs = []
    for row in traces:
        if row["depth"] == 0:
            repair = repair_path(t, y, row["path_indices"], row["lifted"], config.noise_sigma_hz)
            if repair is not None:
                repairs.append(repair)
    write(
        OUT / f"{case}_graph_trace.json",
        dict(
            traces=traces,
            overlapping=overlapping,
            prototype_repairs=repairs,
            replay_tracks=result["tracks"],
            diagnostics=result["diagnostics"],
            GPS_or_satellite_input=False,
        ),
    )
    for row in traces:
        if row["depth"] == 0:
            print(
                "path",
                row["input_points"],
                min(row["path_times"]),
                max(row["path_times"]),
                [(len(a), float(min(a)), float(max(a))) for a in row["model_supports"]],
                flush=True,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        choices=["radio", "orbit", "transition", "peaks", "graph", "figures"],
        required=True,
    )
    parser.add_argument("--case", default="DS23-0342")
    parser.add_argument("--arm", choices=["c0", "fitted_c"], default="c0")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    if args.stage == "radio":
        radio("DS23-0039", 1, 134.0, 240.0)
        radio("DS23-0342", 2, 60.0, 140.0)
    elif args.stage == "orbit":
        orbital(args.case, args.arm)
    elif args.stage == "transition":
        transition(args.arm)
    elif args.stage == "peaks":
        peak_overlap(args.arm)
    elif args.stage == "figures":
        combined_figures()
    else:
        graph_trace()
