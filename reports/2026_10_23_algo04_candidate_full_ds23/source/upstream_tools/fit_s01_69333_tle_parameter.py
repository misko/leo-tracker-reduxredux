"""Bounded exact-SGP4 fits of one orbital element correction plus shared phase."""

import json

import analyze_dsx01_fixed_site as matching
import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from inventory_clipped_phase_cohort import load_study
from investigate_s01_ch4_t001 import OUTPUT as SOURCE
from investigate_s01_ch4_t001 import PRIOR, TARGET
from sgp4.api import WGS72, Satrec

from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    julian_day_from_utc_ns,
    look_angles,
)
from leo.sky.propagation import ElementSetCatalogue

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUTPUT = SOURCE / "tle_parameter_fits"
BOUNDS = {"mean_motion_rev_day": 0.01, "inclination_deg": 0.05, "raan_deg": 0.05,
          "e_cos_omega": 0.0005, "e_sin_omega": 0.0005, "bstar": 0.001}


def perturb(base, parameter, delta):
    """Keep epoch and mean argument of latitude fixed when varying e-vector."""
    e, omega, mean = base.ecco, base.argpo, base.mo
    inclination, node, motion, bstar = base.inclo, base.nodeo, base.no_kozai, base.bstar
    if parameter in ("e_cos_omega", "e_sin_omega"):
        ex, ey = e * np.cos(omega), e * np.sin(omega)
        ex += delta if parameter == "e_cos_omega" else 0
        ey += delta if parameter == "e_sin_omega" else 0
        e = float(np.hypot(ex, ey))
        if delta != 0:
            new_omega = float(np.arctan2(ey, ex) % (2 * np.pi))
            mean = float((mean + omega - new_omega) % (2 * np.pi))
            omega = new_omega
    elif parameter == "mean_motion_rev_day":
        motion += delta * 2 * np.pi / 1440
    elif parameter == "inclination_deg":
        inclination += np.deg2rad(delta)
    elif parameter == "raan_deg":
        node += np.deg2rad(delta)
    elif parameter == "bstar":
        bstar += delta
    elif parameter != "phase_only":
        raise ValueError(parameter)
    sat = Satrec()
    sat.sgp4init(WGS72, base.operationmode, base.satnum,
                 (base.jdsatepoch - 2433281.5) + base.jdsatepochF,
                 bstar, base.ndot, base.nddot, e, omega, inclination, mean, motion, node)
    # Preserve the exact split epoch rather than accepting float date rounding.
    sat.jdsatepoch, sat.jdsatepochF = base.jdsatepoch, base.jdsatepochF
    return sat


def common_epoch_elements(sat, utc_ns):
    jd, fr = julian_day_from_utc_ns(np.array([utc_ns]))
    code, _, _ = sat.sgp4(float(jd[0]), float(fr[0]))
    assert code == 0
    return dict(semi_major_axis_km=sat.am * sat.radiusearthkm,
                eccentricity=sat.em, inclination_deg=np.rad2deg(sat.im),
                raan_deg=np.rad2deg(sat.Om), e_cos_omega=sat.em * np.cos(sat.om),
                e_sin_omega=sat.em * np.sin(sat.om),
                argument_latitude_deg=np.rad2deg((sat.om + sat.mm) % (2 * np.pi)),
                mean_motion_rev_day=sat.nm * 1440 / (2 * np.pi))


def exact_frequency(sat, origin, times, phase):
    cat = ElementSetCatalogue(("STARLINK-37818",), (69333,), (sat,))
    p, v, usable = matching.ecef_states(cat, origin, times + phase)
    assert usable.all()
    angle = EARTH_ROTATION_RAD_S * phase
    for array in (p, v):
        x, y = array[..., 0].copy(), array[..., 1].copy()
        array[..., 0] = np.cos(angle) * x - np.sin(angle) * y
        array[..., 1] = np.sin(angle) * x + np.cos(angle) * y
    observer = geodetic_to_ecef_km(matching.LATITUDE, matching.LONGITUDE, 0)
    _, elevation, _, rate = look_angles(p, v, observer,
                                       ecef_to_enu_matrix(matching.LATITUDE, matching.LONGITUDE))
    return -11.5e9 / 299792.458 * rate[0], elevation[0]


def run():
    OUTPUT.mkdir(exist_ok=True)
    source = json.loads((SOURCE / "bracketing_tles.json").read_text())
    base = Satrec.twoline2rv(*source["past"]["69333"]["lines"])
    future = Satrec.twoline2rv(*source["first_future_epoch"]["69333"]["lines"])
    write(OUTPUT / "common_epoch_elements.json", dict(
        reference_time_s=65,
        past=common_epoch_elements(base, source["anchor_utc_ns"] + 65_000_000_000),
        future=common_epoch_elements(future, source["anchor_utc_ns"] + 65_000_000_000),
        raw_past=dict(e=base.ecco, argument_perigee_deg=np.rad2deg(base.argpo),
                      mean_motion_rev_day=base.no_kozai * 1440 / (2 * np.pi)),
        raw_future=dict(e=future.ecco, argument_perigee_deg=np.rad2deg(future.argpo),
                        mean_motion_rev_day=future.no_kozai * 1440 / (2 * np.pi)),
    ))
    arms = {}
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        study, *_ = load_study("DSX01-S01", fc)
        fit = json.loads((PRIOR / arm / "fit_cap_2.7.json").read_text())
        assoc = json.loads((PRIOR / arm / "association_cap_2.7.json").read_text())
        keys = [r["component"] for r in assoc["association"]["rows"]
                if r["candidate_norad"] == 69333 and r["active_curvature"]]
        tracks = [t for t in study.tracks if t["key"] in keys]
        beta = np.array(fit["beta"])
        ys = []
        for t in tracks:
            g = matching.group(t)
            hw = beta[g] + beta[g + 4] * (t["times"] - 150) / 150
            if len(beta) == 9:
                hw += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
            ys.append(t["values"] - hw)
        arms[arm] = dict(fit=fit, tracks=tracks, y=ys)
    assert [t["key"] for t in arms["c0"]["tracks"]] == [
        t["key"] for t in arms["fitted_c"]["tracks"]]
    tracks = arms["c0"]["tracks"]
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    cases = dict(all_curves=list(range(len(tracks))),
                 omit_target=[i for i, t in enumerate(tracks) if t["key"] != TARGET])
    knots = np.arange(np.floor(min(times)) - 17, np.ceil(max(times)) + 18)
    cache = {}

    def frequency(parameter, delta, phases):
        sat = perturb(base, parameter, delta)
        cat = ElementSetCatalogue(("STARLINK-37818",), (69333,), (sat,))
        key = parameter, round(float(delta), 14)
        if key not in cache:
            p, v, usable = matching.ecef_states(cat, source["anchor_utc_ns"], knots)
            assert usable.all()
            cache[key] = dict(time_s=knots, position_km=p, velocity_km_s=v)
        sky = cache[key]
        many = dict(time_s=knots,
                    position_km=np.broadcast_to(sky["position_km"], (len(phases), len(knots), 3)),
                    velocity_km_s=np.broadcast_to(sky["velocity_km_s"],
                                                 (len(phases), len(knots), 3)))
        geom = prepare_phase_geometry(many, times, np.array(phases))
        f, *_ = phase_linear_frequency(geom, matching.LATITUDE, matching.LONGITUDE)
        return f

    def evaluate(parameter, delta, phases, arm, case):
        f = frequency(parameter, delta, phases)
        rss = np.zeros(len(phases))
        for k in cases[case]:
            t = tracks[k]
            residual = arms[arm]["y"][k] - t["rf_hz"] / 11.5e9 * f[:, np.searchsorted(
                times, t["times"])]
            residual -= residual.mean(axis=1)[:, None]
            rss += np.sum(residual**2, axis=1)
        j = int(np.argmin(rss))
        return dict(delta=float(delta), phase_s=float(phases[j]), rss=float(rss[j]))

    results = {}
    models = ["phase_only", *BOUNDS]
    for parameter in models:
        bound = BOUNDS.get(parameter, 0)
        for arm in arms:
            for case in cases:
                best = None
                phases = np.linspace(-15, 15, 121)
                for delta in np.linspace(-bound, bound, 21) if bound else [0]:
                    row = evaluate(parameter, delta, phases, arm, case)
                    if best is None or row["rss"] < best["rss"]:
                        best = row
                dstep, pstep = bound / 10, 0.25
                jd, fr = julian_day_from_utc_ns(np.array([source["anchor_utc_ns"]
                                                        + 65_000_000_000]))
                elapsed_s = ((jd[0] - base.jdsatepoch) + (fr[0] - base.jdsatepochF)) * 86400
                motion_rev_day = base.no_kozai * 1440 / (2 * np.pi)
                for _ in range(3):
                    anchor_delta, anchor_phase = best["delta"], best["phase_s"]
                    deltas = np.linspace(max(-bound, best["delta"] - dstep),
                                         min(bound, best["delta"] + dstep), 9) if bound else [0]
                    for delta in deltas:
                        center = anchor_phase
                        if parameter == "mean_motion_rev_day":
                            # Follow n/phase covariance rather than trapping the
                            # refinement in an axis-aligned slice of the ridge.
                            center -= elapsed_s / motion_rev_day * (delta - anchor_delta)
                        if not -15 - pstep <= center <= 15 + pstep:
                            continue
                        phases = np.linspace(max(-15, center - pstep),
                                             min(15, center + pstep), 9)
                        row = evaluate(parameter, delta, phases, arm, case)
                        if row["rss"] < best["rss"]:
                            best = row
                    dstep /= 4
                    pstep /= 4
                f = frequency(parameter, best["delta"], [best["phase_s"]])[0]
                exact_f, elevation = exact_frequency(perturb(base, parameter, best["delta"]),
                                                     source["anchor_utc_ns"], times,
                                                     best["phase_s"])
                interpolation_error = float(np.max(abs(exact_f - f)))
                assert interpolation_error < 1
                f = exact_f
                rr = []
                for k, t in enumerate(tracks):
                    q = t["rf_hz"] / 11.5e9
                    raw = arms[arm]["y"][k] - q * f[np.searchsorted(times, t["times"])]
                    alias = round(-float(np.mean(raw)) / matching.PERIOD)
                    bias = float(np.mean(raw)) + alias * matching.PERIOD
                    residual = raw - np.mean(raw)
                    noise = matching.noise_screen(residual, t["times"])
                    rms = float(np.sqrt(np.mean(residual**2)))
                    visible = bool(np.min(elevation[np.searchsorted(times, t["times"])]) >= 0)
                    rr.append(dict(component=t["key"], points=len(residual), rms_hz=rms,
                                   bias_hz=bias, residual_hz=residual, times_s=t["times"],
                                   diagnostics=noise, used_for_fit=k in cases[case],
                                   visible=visible,
                                   passing=bool(visible and rms <= 450 and abs(bias) <= 3000
                                                and noise["noise_screen_pass"])))
                count = sum(len(tracks[k]["times"]) for k in cases[case])
                params = len(cases[case]) + 1 + bool(bound)
                best["rss"] = sum(r["points"] * r["rms_hz"]**2 for r in rr if r["used_for_fit"])
                best.update(parameter=parameter, bound=bound, parameter_count=params,
                            interpolation_error_max_hz=interpolation_error,
                            fit_points=count, bic=float(count * np.log(best["rss"] / count)
                                                        + params * np.log(count)), rows=rr,
                            at_bound=bool(bound and abs(best["delta"]) >= 0.99 * bound))
                results[f"{arm}/{case}/{parameter}"] = best
        cache.clear()
        write(OUTPUT / "results.json", results)
        print(json.dumps(dict(parameter=parameter, fits={
            k: {f: r[f] for f in ("delta", "phase_s", "bic", "at_bound")}
            for k, r in results.items() if k.endswith("/" + parameter)})), flush=True)
    write(OUTPUT / "protocol.json", dict(
        causal_tle_only_for_fitting=True,
        future_tle_comparison_not_used_for_fit_direction_or_bounds=True,
        bounds=BOUNDS, phase_range_s=[-15, 15],
        curved_tracks=9, curved_points=254, no_linear_calibration=True,
        c0_and_fitted_c_same_points_candidates_bounds_budgets=True,
        receiver_band_coefficients_frozen=True, one_orbital_parameter_plus_phase=True,
        constants_per_track_counted_in_bic=True, no_empirical_frequency_rate_in_orbital_models=True,
        e_vector_changes_preserve_mean_argument_of_latitude_at_original_tle_epoch=True,
        original_tle_epoch_preserved=True, original_tle_not_overwritten=True,
        finite_boxes_are_sensitivity_ranges_not_calibrated_orbit_covariance=True,
        global_optimum_not_proven=True, scan_hardware_already_fitted_before_transfer=True,
    ))
    render(results)


def render(results):
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
    models = ["phase_only", *BOUNDS]
    vals = [results[f"fitted_c/all_curves/{m}"] for m in models]
    base_bic = vals[0]["bic"]
    axes[0].bar(models, [base_bic - r["bic"] for r in vals], color="steelblue")
    rate = json.loads((SOURCE / "fitted_c/shared_shape_diagnostics.json").read_text())[
        "all_curves/shared_linear_rate"]
    axes[0].axhline(base_bic - rate["bic"], color="darkorange", ls="--",
                    label="One empirical shared frequency slope")
    axes[0].legend(fontsize=8)
    axes[0].set(ylabel="BIC improvement over phase alone",
                title="One extra orbital parameter per model")
    axes[0].tick_params(axis="x", rotation=20)
    for m in models:
        r = next(r for r in results[f"fitted_c/omit_target/{m}"]["rows"]
                 if r["component"] == TARGET)
        axes[1].plot(r["times_s"], r["residual_hz"], ".-", label=m, alpha=0.8)
    axes[1].axhline(0, color="black", lw=0.8)
    axes[1].set(xlabel="Seconds from scan start", ylabel="Target residual (Hz)",
                title="Fit other eight curved tracks; predict omitted CH4 T001 (constant profiled)")
    axes[1].legend(fontsize=8, ncol=3)
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.suptitle("DSX01 S01 / NORAD 69333 — direct SGP4 element sensitivity\n"
                 "Causal TLE, supplied GPS, frozen hardware; no added frequency slope")
    fig.savefig(OUTPUT / "orbital_parameter_comparison.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    run()
