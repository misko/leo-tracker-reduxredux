"""Jointly fit location and regularized satellite phase-rate uncertainty.

The prior mean and scale come from the sealed pre-target catalogue-history
experiment.  Randomized RF fitting observations update one rate correction per
satellite; held-out RF and the receiver reference coordinate do not participate.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import fit
from replay_regional_doppler import digest, state_arrays, write_json
from scipy.optimize import least_squares

from leo.analysis.research.doppler_error_budget import profile
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region
from leo.sky.propagation import parse_element_sets


def quadratic_phase_state(centre, minus, plus, phase_s):
    phase_s = np.asarray(phase_s)[:, None]
    return centre + 0.5 * (plus - minus) * phase_s + 0.5 * (plus + minus - 2 * centre) * phase_s**2


def robust_residual(residual, scale_hz=250.0):
    return residual * np.sqrt(2 / (np.sqrt(1 + (residual / scale_hz) ** 2) + 1))


def fit_uncertainty(
    data,
    sensitivity,
    region,
    initial,
    source,
    age_h,
    eligible,
    prior_sigma,
    prior_residual_scale_hz=100.0,
):
    training = data["training"].astype(bool)
    labels = np.unique(source[eligible])
    index = {int(label): number for number, label in enumerate(labels)}
    variable = np.asarray([index.get(int(label), -1) for label in source])

    def states(value):
        rate = np.zeros(len(source))
        chosen = variable >= 0
        rate[chosen] = value[2:][variable[chosen]]
        phase = rate * age_h
        return (
            quadratic_phase_state(data["p"], sensitivity["p-1"], sensitivity["p1"], phase),
            quadratic_phase_state(data["v"], sensitivity["v-1"], sensitivity["v1"], phase),
        )

    def rf_residual(value):
        receiver = region.points([value[0]], [value[1]]).ecef_km[0]
        p, v = states(value)
        delta = p - receiver
        prediction = (
            -REFERENCE_RF_HZ
            / LIGHT_KM_S
            * np.sum(delta * v, axis=1)
            / np.linalg.norm(delta, axis=1)
        )
        return profile(data["y"] - prediction, data["segment"], training)

    def objective(value):
        radio = robust_residual(rf_residual(value)[training])
        prior = prior_residual_scale_hz * value[2:] / prior_sigma
        return np.concatenate([radio, prior])

    lower = [-region.width_km / 2, -region.height_km / 2] + [-0.25] * len(labels)
    upper = [region.width_km / 2, region.height_km / 2] + [0.25] * len(labels)
    answer = least_squares(
        objective,
        [*initial, *np.zeros(len(labels))],
        bounds=(lower, upper),
        jac_sparsity=None,
        diff_step=1e-5,
        xtol=1e-10,
        ftol=1e-10,
        gtol=1e-5,
        max_nfev=60,
    )
    residual = rf_residual(answer.x)
    latitude, longitude = region.coordinates(*answer.x[:2])
    return {
        "x_km": answer.x[:2].tolist(),
        "latitude_deg": float(latitude),
        "longitude_deg": float(longitude),
        "training_rms_hz": float(np.sqrt(np.mean(residual[training] ** 2))),
        "evaluation_rms_hz": float(np.sqrt(np.mean(residual[~training] ** 2))),
        "converged": bool(answer.success),
        "nfev": answer.nfev,
        "fitted_satellites": len(labels),
        "free_parameters": 2 + len(labels),
        "phase_rate_sigma_s_h": prior_sigma,
        "prior_residual_scale_hz": prior_residual_scale_hz,
        "rf_robust_loss_scale_hz": 250.0,
        "phase_rate_bounds_s_h": [-0.25, 0.25],
        "rate_corrections_s_h": {
            str(label): float(answer.x[2 + index[int(label)]]) for label in labels
        },
        "rate_at_bound_count": int(np.sum(abs(answer.x[2:]) > 0.249)),
    }


def fixed_position_rms(data, region, x_km):
    training = data["training"].astype(bool)
    receiver = region.points([x_km[0]], [x_km[1]]).ecef_km[0]
    delta = data["p"] - receiver
    prediction = (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(delta * data["v"], axis=1)
        / np.linalg.norm(delta, axis=1)
    )
    residual = profile(data["y"] - prediction, data["segment"], training)
    return {
        "training_rms_hz": float(np.sqrt(np.mean(residual[training] ** 2))),
        "evaluation_rms_hz": float(np.sqrt(np.mean(residual[~training] ** 2))),
    }


def exact_states(data, rows, phases, targets, rate_corrections):
    result = {key: value.copy() for key, value in data.items()}
    for episode, (row, target, phase_mean) in enumerate(zip(rows, targets, phases, strict=True)):
        mask = data["episode"] == episode
        age_h = (row["capture_start_utc_ns"] - row["winning_epoch_utc_ns"]) / 3_600_000_000_000
        phase = phase_mean + rate_corrections.get(str(target["norad"]), 0.0) * age_h
        catalogue = parse_element_sets(row["winning_tle_text"])
        for shift in [0.0, -0.5, 0.5]:
            p, v, valid = state_arrays(
                catalogue,
                [0],
                row["capture_start_utc_ns"],
                data["time"][mask],
                orbit_time_s=phase,
                clock_s=shift,
            )
            if len(valid) != 1:
                raise ValueError("invalid exact phase-corrected orbit")
            suffix = "" if shift == 0 else str(shift)
            result["p" + suffix][mask] = p[0]
            result["v" + suffix][mask] = v[0]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ["analysis", "states", "causal", "parent", "output"]:
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("fresh output required")
    analysis = json.loads(args.analysis.read_text())
    parent = json.loads((args.parent / "inference.json").read_text())
    data = dict(np.load(args.states))
    raw_rows = json.loads((args.causal / "strict-reranking.json").read_text())["rows"]
    lookup = {(row["session_id"], row["episode_id"]): row for row in raw_rows}
    rows = [lookup[(row["session_id"], row["episode_id"])] for row in parent["assignments"]]
    targets = analysis["targets"]
    if any(
        (target["session_id"], target["episode_id"])
        != (assignment["session_id"], assignment["episode_id"])
        for target, assignment in zip(targets, parent["assignments"], strict=True)
    ):
        raise ValueError("target ordering mismatch")
    for episode, row in enumerate(rows):
        observed = np.unique(data["norad"][data["episode"] == episode])
        if observed.tolist() != [row["best_norad"]]:
            raise ValueError("state NORAD does not match strict causal winner")
    phases = [target["predicted_phase_s"] for target in targets]
    sensitivity = {key: np.empty_like(data[key[0]]) for key in ["p-1", "v-1", "p1", "v1"]}
    for episode, (row, phase) in enumerate(zip(rows, phases, strict=True)):
        mask = data["episode"] == episode
        catalogue = parse_element_sets(row["winning_tle_text"])
        for shift in [-1.0, 1.0]:
            p, v, valid = state_arrays(
                catalogue,
                [0],
                row["capture_start_utc_ns"],
                data["time"][mask],
                orbit_time_s=phase + shift,
            )
            if len(valid) != 1:
                raise ValueError("invalid phase sensitivity orbit")
            label = str(int(shift)).replace("-", "-")
            sensitivity["p" + label][mask] = p[0]
            sensitivity["v" + label][mask] = v[0]
    source = data["norad"].astype(int)
    ages = np.asarray(
        [
            (row["capture_start_utc_ns"] - row["winning_epoch_utc_ns"]) / 3_600_000_000_000
            for row in rows
        ]
    )[data["episode"].astype(int)]
    episodes_per_source = {
        int(norad): len(np.unique(data["episode"][source == norad])) for norad in np.unique(source)
    }
    prior_sigma = analysis["frozen_model"]["winner"]["validation_rms_rate_error_s_h"]
    point = next(
        model
        for model in analysis["models"]
        if model["selection"] == "all"
        and model["orbit_model"] == "causal_phase_prior"
        and model["clock_model"] == "fixed"
    )
    region = Region(**parent["region"])
    results = []
    mode_eligibility = [
        ("repeated_satellites", np.asarray([episodes_per_source[x] >= 2 for x in source])),
        ("all_satellites_flexibility_control", np.ones(len(source), bool)),
    ]
    for mode, eligible in mode_eligibility:
        result = fit_uncertainty(
            data,
            sensitivity,
            region,
            point["x_km"],
            source,
            ages,
            eligible,
            prior_sigma,
        )
        exact = exact_states(data, rows, phases, targets, result["rate_corrections_s_h"])
        verification = fit(
            exact,
            region,
            result["x_km"],
            "observation",
            True,
        )
        result.update(
            mode=mode,
            exact_state_at_joint_position=fixed_position_rms(exact, region, result["x_km"]),
            exact_fixed_rate_verification=verification,
        )
        results.append(result)
        print(mode, result["evaluation_rms_hz"], verification["evaluation_rms_hz"], flush=True)
    stability = []
    for mode, eligible in mode_eligibility:
        for grouping, group in [("norad", source), ("session", data["session"].astype(int))]:
            for fold in range(4):
                retained = group % 4 != fold
                subset_data = {key: value[retained] for key, value in data.items()}
                subset_sensitivity = {key: value[retained] for key, value in sensitivity.items()}
                check = fit_uncertainty(
                    subset_data,
                    subset_sensitivity,
                    region,
                    point["x_km"],
                    source[retained],
                    ages[retained],
                    eligible[retained],
                    prior_sigma,
                )
                stability.append({"mode": mode, "grouping": grouping, "fold": fold, **check})
                print(mode, grouping, fold, check["evaluation_rms_hz"], flush=True)
    prior_scale_sensitivity = []
    for factor in [0.5, 2.0]:
        for mode, eligible in mode_eligibility:
            check = fit_uncertainty(
                data,
                sensitivity,
                region,
                point["x_km"],
                source,
                ages,
                eligible,
                prior_sigma * factor,
            )
            prior_scale_sensitivity.append({"mode": mode, "prior_sigma_factor": factor, **check})
            print(mode, "prior", factor, check["evaluation_rms_hz"], flush=True)
    write_json(
        args.output,
        {
            "strictly_causal": True,
            "evaluation_location_used": False,
            "randomized_heldout_used_to_fit": False,
            "identity_policy": (
                "fixed strict-causal catalogue winners; identities are not inferred by this model"
            ),
            "receiver_clock_model": "fixed UTC; no fitted receiver-clock correction",
            "profiled_nuisance_parameters": {
                "source_frequency_offsets": int(len(np.unique(data["segment"]))),
                "description": "one training-estimated additive frequency offset per RF segment",
            },
            "observations": {
                "total": int(len(data["y"])),
                "fitting": int(np.sum(data["training"].astype(bool))),
                "randomized_evaluation": int(np.sum(~data["training"].astype(bool))),
                "episodes": int(len(np.unique(data["episode"]))),
                "satellites": int(len(np.unique(source))),
            },
            "analysis_digest": digest(args.analysis),
            "states_digest": digest(args.states),
            "prior_sigma_source": "pre-target temporal validation RMS phase-rate error",
            "results": results,
            "stability": stability,
            "prior_scale_sensitivity": prior_scale_sensitivity,
        },
    )


if __name__ == "__main__":
    main()
