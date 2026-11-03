"""Test low-dimensional shared physical-shape sensitivities, without adoption.

Models use all measured-curved nominees, explicit component constants, a shared
phase, and at most two shared shape coefficients. Leave-one-curve transfer is
conditional on the existing frozen scan hardware, not independent validation.
"""

import argparse
import json

import analyze_dsx01_fixed_site as matching
import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from inventory_clipped_phase_cohort import load_study
from investigate_s01_ch4_t001 import OUTPUT, PRIOR, TARGET

from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.sky.frames import geodetic_to_ecef_km

matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODELS = {"phase_only": [], "shared_linear_rate": ["rate"],
          "doppler_scale": ["scale"], "radial_cross_unbounded": ["radial", "cross"],
          "radial_cross_within_5km": ["radial", "cross"]}
BASE_OUTPUT = OUTPUT


def box_lstsq2(x, y, bound):
    candidates = []
    unconstrained = np.linalg.lstsq(x, y, rcond=None)[0]
    if np.max(abs(unconstrained)) <= bound:
        candidates.append(unconstrained)
    for fixed in (0, 1):
        free = 1 - fixed
        for value in (-bound, bound):
            coef = np.zeros(2)
            coef[fixed] = value
            denominator = x[:, free] @ x[:, free]
            coef[free] = np.clip(x[:, free] @ (y - value * x[:, fixed]) / denominator,
                                 -bound, bound) if denominator else 0
            candidates.append(coef)
    return min(candidates, key=lambda c: np.sum((y - x @ c)**2))


def run(*, bank_kind="past"):
    OUTPUT.mkdir(exist_ok=True)
    common_keys = None
    all_summaries = {}
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        study, *_ = load_study("DSX01-S01", fc)
        if bank_kind == "first_future_epoch":
            with np.load(BASE_OUTPUT / "bank_first_future_epoch.npz") as bank:
                study.sky = {**study.sky, **{k: bank[k] for k in bank.files}}
        fit = json.loads((PRIOR / arm / "fit_cap_2.7.json").read_text())
        assoc = json.loads((PRIOR / arm / "association_cap_2.7.json").read_text())
        keys = [r["component"] for r in assoc["association"]["rows"]
                if r["candidate_norad"] == 69333 and r["active_curvature"]]
        if common_keys is None:
            common_keys = keys
        assert keys == common_keys
        tracks = [t for t in study.tracks if t["key"] in keys]
        times = np.unique(np.concatenate([t["times"] for t in tracks]))
        selected = np.flatnonzero(study.sky["norad"] == 69333)
        sky = {k: study.sky[k][selected] for k in ("position_km", "velocity_km_s")}
        sky["time_s"] = study.sky["time_s"]
        observer = geodetic_to_ecef_km(fit["latitude_deg"], fit["longitude_deg"], 0)
        beta = np.array(fit["beta"])
        measurements, alias = [], []
        for t in tracks:
            g = matching.group(t)
            hw = beta[g] + beta[g + 4] * (t["times"] - 150) / 150
            if len(beta) == 9:
                hw += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
            measurements.append(t["values"] - hw)
        # Alias branch fixed from the current nominal physical prediction.
        base = prepare_phase_geometry(sky, times, np.array([fit["phases_s"][selected[0]]]))
        nominal, *_ = phase_linear_frequency(base, fit["latitude_deg"], fit["longitude_deg"])
        for t, y in zip(tracks, measurements, strict=True):
            pred = t["rf_hz"] / 11.5e9 * nominal[0, np.searchsorted(times, t["times"])]
            alias.append(int(np.round(np.mean(pred - y) / matching.PERIOD)))
        cases = {"all_curves": set(keys), "target_only": {TARGET},
                 "omit_target": set(keys) - {TARGET}}
        best = {(case, model): None for case in cases for model in MODELS}
        for phase_s in np.arange(-3, 1.0001, 0.01):
            geom = prepare_phase_geometry(sky, times, np.array([phase_s]))
            f, _, _ = phase_linear_frequency(geom, fit["latitude_deg"], fit["longitude_deg"])
            p, v = geom.geometry.position_km[0], geom.geometry.velocity_km_s[0]
            omega = np.array([0, 0, EARTH_ROTATION_RAD_S])
            radial = p / np.linalg.norm(p, axis=1)[:, None]
            normal = np.cross(p, v + np.cross(omega, p))
            normal /= np.linalg.norm(normal, axis=1)[:, None]
            radial_dot = (v - radial * np.sum(radial * v, axis=1)[:, None])
            radial_dot /= np.linalg.norm(p, axis=1)[:, None]
            normal_dot = -np.cross(omega, normal)
            los = p - observer
            distance = np.linalg.norm(los, axis=1)
            u = los / distance[:, None]
            rate = np.sum(u * v, axis=1)
            jp = -11.5e9 / 299792.458 * (v - u * rate[:, None]) / distance[:, None]
            jv = -11.5e9 / 299792.458 * u
            bases = dict(rate=times - 65, scale=f[0],
                         radial=np.sum(jp * radial + jv * radial_dot, axis=1),
                         cross=np.sum(jp * normal + jv * normal_dot, axis=1))
            residuals, features = [], {}
            for k, (t, y) in enumerate(zip(tracks, measurements, strict=True)):
                ix = np.searchsorted(times, t["times"])
                q = t["rf_hz"] / 11.5e9
                residuals.append(y + alias[k] * matching.PERIOD - q * f[0, ix])
            for name, columns in MODELS.items():
                features[name] = [np.column_stack([t["rf_hz"] / 11.5e9
                                                   * bases[c][np.searchsorted(times, t["times"])]
                                                   for c in columns]) if columns
                                  else np.empty((len(t["times"]), 0)) for t in tracks]
            for case, members in cases.items():
                use = [k for k, t in enumerate(tracks) if t["key"] in members]
                yy = np.concatenate([residuals[k] - np.mean(residuals[k]) for k in use])
                for model, columns in MODELS.items():
                    xx = np.concatenate([features[model][k] - features[model][k].mean(axis=0)
                                         for k in use])
                    coef = np.linalg.lstsq(xx, yy, rcond=None)[0] if columns else np.array([])
                    if model == "radial_cross_within_5km":
                        coef = box_lstsq2(xx, yy, 5.0)
                    rr = yy - xx @ coef
                    rss = float(rr @ rr)
                    if best[case, model] is not None and rss >= best[case, model]["rss"]:
                        continue
                    rows = []
                    for k, t in enumerate(tracks):
                        residual = residuals[k] - features[model][k] @ coef
                        bias = float(np.mean(residual))
                        residual -= bias
                        noise = matching.noise_screen(residual, t["times"])
                        rms = float(np.sqrt(np.mean(residual**2)))
                        rows.append(dict(component=t["key"], points=len(residual),
                                         rms_hz=rms, bias_hz=bias, residual_hz=residual,
                                         times_s=t["times"], fitted=t["key"] in members,
                                         passing=bool(rms <= 450 and abs(bias) <= 3000
                                                      and noise["noise_screen_pass"]),
                                         diagnostics=noise))
                    best[case, model] = dict(
                        phase_s=float(phase_s), shared_parameters=dict(zip(columns, coef,
                                                                         strict=True)),
                        rss=rss, fit_points=len(yy), parameter_count=len(use) + 1 + len(columns),
                        bic=float(len(yy) * np.log(rss / len(yy))
                                  + (len(use) + 1 + len(columns)) * np.log(len(yy))), rows=rows,
                    )
        summaries = {}
        for (case, model), result in best.items():
            summaries[f"{case}/{model}"] = result
        all_summaries[arm] = summaries
        (OUTPUT / arm).mkdir(exist_ok=True)
        write(OUTPUT / arm / "shared_shape_diagnostics.json", summaries)
        print(json.dumps({k: dict(phase_s=v["phase_s"], parameters=v["shared_parameters"],
                                 bic=v["bic"], target=next(dict(rms=r["rms_hz"],
                                                               passing=r["passing"])
                                                          for r in v["rows"]
                                                          if r["component"] == TARGET))
                          for k, v in summaries.items()}), flush=True)
    if bank_kind == "past":
        render(all_summaries["fitted_c"])
    write(OUTPUT / "shape_protocol.json", dict(
        diagnostic_only=True, calibration_not_adopted=True,
        bank_kind=bank_kind,
        candidate_label_69333_is_hypothesis=True,
        only_raw_measured_curved_members_used=True, hardware_and_gps_fixed=True,
        per_component_constants_counted_in_bic=True,
        displacement_model="constant radial/cross-track displacements in moving RTN frame; "
                           "linear Doppler tangent including basis time derivatives; "
                           "kinematic sensitivity, not a refitted SGP4 orbit",
        transfer_conditional_on_preexisting_hardware=True,
        shared_rate_not_automatically_attributed_to_LNB=True,
        doppler_scale_not_authority_to_change_actual_RF=True,
        c0_fitted_c_matched_observations_candidates_priors_search_budgets=True,
    ))


def render(results):
    family = json.loads((OUTPUT / "fitted_c/family_summary.json").read_text())
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), layout="constrained")
    old = next(r for r in family["current"]["rows"] if r["component"] == TARGET)
    best = next(r for r in family["minimum_target_rms"]["rows"] if r["component"] == TARGET)
    for r, label in [(old, "Current phase"), (best, "Best phase alone")]:
        axes[0, 0].plot(r["times_s"], r["residual_hz"], "o-", ms=3, label=label)
    axes[0, 0].set(title="Target: phase alone leaves structured residuals")
    axes[0, 0].legend(fontsize=8)
    colors = plt.get_cmap("tab10")
    for i, r in enumerate(family["current"]["rows"]):
        axes[0, 1].plot(r["times_s"], r["residual_hz"], ".-", color=colors(i),
                        label=r["component"].replace("S01-RX1-", ""), alpha=0.8)
    axes[0, 1].set(title="Other curved nominees show common residual structure")
    axes[0, 1].legend(fontsize=7, ncol=2)
    for model in MODELS:
        r = next(r for r in results[f"target_only/{model}"]["rows"] if r["component"] == TARGET)
        axes[1, 0].plot(r["times_s"], r["residual_hz"], ".-", label=model, alpha=0.8)
        r = next(r for r in results[f"omit_target/{model}"]["rows"] if r["component"] == TARGET)
        axes[1, 1].plot(r["times_s"], r["residual_hz"], ".-", label=model, alpha=0.8)
    axes[1, 0].set(title="Diagnostic fits to target (extra parameters penalized)")
    axes[1, 1].set(title="Learn shape without target; transfer to its 45 points")
    for ax in axes.flat:
        ax.axhline(0, color="black", lw=0.6)
        ax.set(xlabel="Seconds from scan start", ylabel="Residual CFO (Hz)")
        ax.grid(alpha=0.15)
    axes[1, 0].legend(fontsize=7)
    axes[1, 1].legend(fontsize=7)
    fig.suptitle("DSX01 S01 RX1 CH4 T001 — model diagnosis at supplied GPS\n"
                 "Shared-shape alternatives are diagnostic; no new production association")
    fig.savefig(OUTPUT / "model_diagnosis.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank-kind", choices=("past", "first_future_epoch"), default="past")
    args = parser.parse_args()
    if args.bank_kind != "past":
        OUTPUT = BASE_OUTPUT / "future_shared_shape"
    run(bank_kind=args.bank_kind)
