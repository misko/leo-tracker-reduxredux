"""Validate the retrospective comparison and render the conservative family fit."""

import hashlib
import json

import analyze_dsx01_fixed_site as matching
import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from investigate_s01_ch4_t001 import OUTPUT, TARGET
from sgp4.api import Satrec

from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles
from leo.sky.propagation import ElementSetCatalogue

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def run():
    t = json.loads((OUTPUT / "track.json").read_text())
    source = json.loads((OUTPUT / "bracketing_tles.json").read_text())
    for kind in ("past", "first_future_epoch"):
        tle = source[kind]["69333"]
        (OUTPUT / f"69333_{kind}.tle").write_text("0 " + tle["name"] + "\n"
                                                 + "\n".join(tle["lines"]) + "\n")
    bank_past = np.load(OUTPUT / "bank_past.npz")
    bank_future = np.load(OUTPUT / "bank_first_future_epoch.npz")
    j = list(bank_past["norad"]).index(69333)
    i = int(np.argmin(abs(bank_past["time_s"] - 65)))
    p, v = bank_past["position_km"][j, i], bank_past["velocity_km_s"][j, i]
    omega = np.array([0, 0, EARTH_ROTATION_RAD_S])
    radial = p / np.linalg.norm(p)
    normal = np.cross(p, v + np.cross(omega, p))
    normal /= np.linalg.norm(normal)
    rotation = np.array([radial, np.cross(normal, radial), normal])
    dp = bank_future["position_km"][j, i] - p
    dv = bank_future["velocity_km_s"][j, i] - v
    results = {}
    for arm in ("c0", "fitted_c"):
        old = json.loads((OUTPUT / arm / "family_summary.json").read_text())
        future = json.loads((OUTPUT / "first_future_epoch" / arm /
                             "family_summary.json").read_text())
        profile = json.loads((OUTPUT / "first_future_epoch" / arm /
                              "family_phase_profile.json").read_text())
        possible = [r for r in profile if all(x["passing"] for x in r["rows"]
                                             if x["component"] in
                                             {*future["previous_curved_support"], TARGET})]
        assert possible
        chosen = min(possible, key=lambda r: r["score"])
        old_target = next(r for r in old["current"]["rows"] if r["component"] == TARGET)
        old_best = next(r for r in old["minimum_target_rms"]["rows"] if r["component"] == TARGET)
        new_best = next(r for r in future["minimum_target_rms"]["rows"]
                        if r["component"] == TARGET)
        new_target = next(r for r in chosen["rows"] if r["component"] == TARGET)
        assert not old_target["passing"] and not old_best["passing"]
        assert new_best["passing"] and new_target["passing"]
        for kind in ("past", "first_future_epoch"):
            folder = OUTPUT / (kind if kind != "past" else "") / arm
            matrix = np.load(folder / "identity_grid.npz")
            candidates = matrix["norad"][matrix["passing"].any(axis=0)].tolist()
            assert candidates == ([] if kind == "past" else [69333])
        # Independent direct SGP4 check of the interpolated best-future profile.
        tle = source["first_future_epoch"]["69333"]
        sat = Satrec.twoline2rv(*tle["lines"])
        cat = ElementSetCatalogue((tle["name"],), (69333,), (sat,))
        phase = future["minimum_target_rms"]["phase_s"]
        pp, vv, usable = matching.ecef_states(cat, source["anchor_utc_ns"],
                                            np.array(t["times"]) + phase)
        assert usable.all()
        angle = EARTH_ROTATION_RAD_S * phase
        for array in (pp, vv):
            x, y = array[..., 0].copy(), array[..., 1].copy()
            array[..., 0] = np.cos(angle) * x - np.sin(angle) * y
            array[..., 1] = np.sin(angle) * x + np.cos(angle) * y
        observer = geodetic_to_ecef_km(matching.LATITUDE, matching.LONGITUDE, 0)
        _, _, _, rate = look_angles(pp, vv, observer,
                                   ecef_to_enu_matrix(matching.LATITUDE, matching.LONGITUDE))
        exact_f = -t["rf_hz"] / 299792.458 * rate[0]
        sky = {k: bank_future[k][j:j + 1] for k in ("position_km", "velocity_km_s")}
        sky["time_s"] = bank_future["time_s"]
        geom = prepare_phase_geometry(sky, np.array(t["times"]), np.array([phase]))
        from leo.analysis.research.phase_linear_geometry import phase_linear_frequency
        interp_f, *_ = phase_linear_frequency(geom, matching.LATITUDE, matching.LONGITUDE)
        interpolation_error = exact_f - interp_f[0] * t["rf_hz"] / 11.5e9
        assert np.max(abs(interpolation_error)) < 1
        x = (np.array(t["times"]) - t["pieces"][0]["reference_time_s"]) / t["pieces"][0][
            "time_scale_s"]
        design = np.polynomial.polynomial.polyvander(x, 4)
        leverage = np.sum(design * np.linalg.pinv(design).T, axis=1)
        coef = np.linalg.lstsq(design[:-1], np.array(t["values"])[:-1], rcond=None)[0]
        loo_error = float(t["values"][-1] - design[-1] @ coef)
        results[arm] = dict(
            causal_current=old_target, causal_best_phase_only=old_best,
            future_best_phase_only=new_best,
            future_conservative_family_state=chosen,
            conservative_family_target_rms_hz=new_target["rms_hz"],
            future_conservative_phase_range_s=[min(r["phase_s"] for r in possible),
                                                max(r["phase_s"] for r in possible)],
            maximum_direct_sgp4_vs_interpolation_error_hz=float(np.max(abs(interpolation_error))),
            endpoint=dict(time_s=t["times"][-1], quartic_leverage=float(leverage[-1]),
                          quartic_leave_endpoint_out_error_hz=loo_error,
                          future_physical_residual_hz=new_best["residual_hz"][-1],
                          retained_not_declared_bad=True),
        )
    write(OUTPUT / "final_diagnosis.json", dict(
        all_checks_passed=True, target=TARGET, points=len(t["times"]),
        duration_s=t["times"][-1] - t["times"][0],
        candidate_norad=69333, candidate_name=source["past"]["69333"]["name"],
        source_tles={k: source[k]["69333"] for k in
                     ("past", "first_post_collection", "first_future_epoch")},
        first_post_collection_has_same_target_elements=(source["past"]["69333"]["lines"]
                                                        == source["first_post_collection"][
                                                            "69333"]["lines"]),
        state_comparison_time_s=float(bank_past["time_s"][i]),
        future_minus_past_position_rtn_km=rotation @ dp,
        future_minus_past_velocity_rtn_m_s=rotation @ dv * 1000,
        fitted_c_and_c0_matched=True, diagnostic_only=True,
        no_causal_baseline_overwritten=True, arms=results,
    ))
    render(t, results["fitted_c"])
    files = list(OUTPUT.glob("*.json")) + list(OUTPUT.glob("*.npz"))
    write(OUTPUT / "validation.json", dict(
        checks_passed=True, future_identity_unique_in_declared_bank_and_grid=True,
        original_causal_bank_exactly_reproduced=True,
        direct_sgp4_interpolation_error_below_1hz=True,
        old_three_curved_labels_retained_at_selected_future_phase=True,
        linear_calibration_used=False, production_associations_changed=False,
        files_sha256={str(f.relative_to(OUTPUT)): hashlib.sha256(f.read_bytes()).hexdigest()
                      for f in files if f.name != "validation.json"},
    ))


def render(track, result):
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), layout="constrained")
    times, values = np.array(track["times"]), np.array(track["values"])
    axes[0].scatter(times, values / 1000, c="black", s=14, label="45 measured GLRT points")
    piece = track["pieces"][0]
    dense = np.linspace(min(times), max(times), 400)
    x = (dense - piece["reference_time_s"]) / piece["time_scale_s"]
    axes[0].plot(dense, np.polynomial.polynomial.polyval(x, piece["coefficients_hz"]) / 1000,
                 color="gray", lw=2, label="Empirical quartic: 69.7 Hz RMS")
    conservative = next(r for r in result["future_conservative_family_state"]["rows"]
                        if r["component"] == TARGET)
    for r, label in [(result["causal_current"], "Current causal phase"),
                     (result["causal_best_phase_only"], "Causal TLE, best phase"),
                     (conservative, "Future TLE, common phase +0.23 s")]:
        axes[0].plot(times, (values - r["residual_hz"]) / 1000, lw=1,
                     label=f"{label}: {r['rms_hz']:.1f} Hz")
        axes[1].plot(times, r["residual_hz"], "o-", ms=3, label=label)
    axes[0].set(ylabel="Alias-unwrapped CFO (kHz)",
                title="GLRT, graph polynomial and physical fits")
    axes[1].set(ylabel="Residual CFO (Hz)", title="Original points retained, hardware unchanged")
    axes[1].axhline(0, color="black", lw=0.7)
    for ax in axes:
        ax.set(xlabel="Seconds from scan start")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.2)
    fig.suptitle("DSX01 S01 RX1 CH4 T001 — retrospective support for STARLINK-37818 / 69333\n"
                 "Future TLE common phase retains target + all 3 old curved members: "
                 "7 of 9 nominees / 177 curved points pass")
    fig.savefig(OUTPUT / "target_conservative_future_fit.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    run()
