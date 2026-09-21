"""Test a pre-capture-only orbital phase-error prior on the frozen RF cohort.

The predictor is frozen from catalogue transitions collected before the first
target capture.  Target RF, target held-out observations, later TLEs, and the
receiver reference coordinate never choose the predictor or its coefficients.
Later TLEs are used only for a separately labelled diagnostic.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import fit
from replay_regional_doppler import digest, state_arrays, write_json
from scipy.optimize import least_squares
from study_orbit_update_modes import raw_state, rms

from leo.analysis.research.doppler_error_budget import profile
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region
from leo.sky.propagation import parse_element_set_records, parse_element_sets

NS_HOUR = 3_600_000_000_000


def collection_ns(path):
    return int(path.name.split("-", 1)[0])


def tle_key(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return tuple(line for line in lines if line.startswith(("1 ", "2 ")))


def phase_seconds(old_text, new_text, epoch_ns):
    """First-order along-track shift taking old position toward new position."""
    old = parse_element_sets(old_text)
    new = parse_element_sets(new_text)
    op, ov = raw_state(old, epoch_ns, np.array([0.0]))
    np_, _ = raw_state(new, epoch_ns, np.array([0.0]))
    delta = np_[0] - op[0]
    velocity = ov[0]
    return float(np.dot(delta, velocity) / np.dot(velocity, velocity))


def oracle_phase_seconds(old_text, new_text, epoch_ns, times):
    """Fit phase to a later TLE for a labelled noncausal upper-bound diagnostic."""
    old = parse_element_sets(old_text)
    new = parse_element_sets(new_text)
    target, _ = raw_state(new, epoch_ns, times)
    initial = np.clip(phase_seconds(old_text, new_text, epoch_ns), -119.9, 119.9)
    answer = least_squares(
        lambda value: (raw_state(old, epoch_ns, times + value[0])[0] - target).ravel(),
        [initial],
        bounds=([-120], [120]),
        diff_step=1e-4,
    )
    if not answer.success:
        raise ValueError("future-orbit phase fit failed")
    return float(answer.x[0])


def read_histories(paths, wanted, last_capture_ns):
    histories = defaultdict(dict)
    for number, path in enumerate(sorted(paths, key=collection_ns)):
        collected = collection_ns(path)
        if collected >= last_capture_ns:
            continue
        for record in parse_element_set_records(path.read_text()):
            if record.satellite_number not in wanted:
                continue
            current = histories[record.satellite_number].get(record.text)
            if current is None or collected < current["first_collected_utc_ns"]:
                cat = parse_element_sets(record.text)
                histories[record.satellite_number][record.text] = {
                    "text": record.text,
                    "epoch_utc_ns": int(cat.element_epoch_utc_ns()[0]),
                    "first_collected_utc_ns": collected,
                }
        if number % 20 == 0:
            print("archive", number + 1, flush=True)
    return {norad: list(records.values()) for norad, records in histories.items()}


def sequence_before(records, cutoff_ns):
    eligible = [
        row
        for row in records
        if row["epoch_utc_ns"] < cutoff_ns and row["first_collected_utc_ns"] < cutoff_ns
    ]
    by_epoch = {}
    for row in eligible:
        key = row["epoch_utc_ns"]
        if (
            key not in by_epoch
            or row["first_collected_utc_ns"] > by_epoch[key]["first_collected_utc_ns"]
        ):
            by_epoch[key] = row
    return [by_epoch[key] for key in sorted(by_epoch)]


def transition_rates(sequence):
    result = []
    for old, new in zip(sequence[:-1], sequence[1:], strict=True):
        age_h = (new["epoch_utc_ns"] - old["epoch_utc_ns"]) / NS_HOUR
        if not 1 <= age_h <= 72:
            continue
        tau = phase_seconds(old["text"], new["text"], new["epoch_utc_ns"])
        if np.isfinite(tau) and abs(tau) <= 30:
            old_sat = parse_element_sets(old["text"]).satellites[0]
            new_sat = parse_element_sets(new["text"]).satellites[0]
            rate = tau / age_h
            result.append(
                {
                    "rate_s_h": rate,
                    "age_h": age_h,
                    "phase_s": tau,
                    "feature": [
                        rate,
                        float(new_sat.bstar),
                        float(new_sat.no_kozai),
                        float(new_sat.ecco),
                        float((new_sat.bstar - old_sat.bstar) / age_h),
                        float((new_sat.no_kozai - old_sat.no_kozai) / age_h),
                        float((new_sat.ecco - old_sat.ecco) / age_h),
                        age_h,
                    ],
                }
            )
    return result


def robust_affine(x, y):
    x, y = np.asarray(x), np.asarray(y)
    scale = max(float(np.median(np.abs(y - np.median(y)))), 1e-4)
    answer = least_squares(
        lambda z: y - z[0] - z[1] * x,
        [float(np.median(y)), 0.0],
        loss="soft_l1",
        f_scale=scale,
    )
    if not answer.success:
        raise ValueError("historical phase-rate fit failed")
    return answer.x


def ridge_model(x, y, alpha):
    x, y = np.asarray(x), np.asarray(y)
    centre = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale < 1e-12] = 1.0
    z = (x - centre) / scale
    y_centre = float(np.median(y))
    residual_scale = max(float(np.median(abs(y - y_centre))), 1e-4)
    answer = least_squares(
        lambda coefficient: np.concatenate(
            [y - y_centre - z @ coefficient, np.sqrt(alpha) * coefficient]
        ),
        np.zeros(z.shape[1]),
        loss="soft_l1",
        f_scale=residual_scale,
    )
    if not answer.success:
        raise ValueError("historical ridge phase-rate fit failed")
    return {
        "name": "ridge_features",
        "alpha": alpha,
        "intercept_s_h": y_centre,
        "feature_centre": centre.tolist(),
        "feature_scale": scale.tolist(),
        "coefficient": answer.x.tolist(),
    }


def predict_rate(model, recent_rate, feature=None):
    if model["name"] == "zero":
        return 0.0
    if model["name"] == "median":
        return model["intercept_s_h"]
    if model["name"] == "persistence":
        return recent_rate
    if model["name"] == "ridge_features":
        value = np.asarray(feature)
        centre = np.asarray(model["feature_centre"])
        scale = np.asarray(model["feature_scale"])
        return float(
            model["intercept_s_h"]
            + np.dot((value - centre) / scale, np.asarray(model["coefficient"]))
        )
    return model["intercept_s_h"] + model["slope"] * recent_rate


def select_candidate(candidates):
    return min(candidates, key=lambda row: row["validation_median_absolute_rate_error_s_h"]).copy()


def freeze_model(histories, cutoff_ns):
    train_x, train_feature, train_y, valid_x, valid_feature, valid_y = [], [], [], [], [], []
    transition_count = 0
    for records in histories.values():
        rates = transition_rates(sequence_before(records, cutoff_ns))
        transition_count += len(rates)
        pairs = [
            (a["rate_s_h"], a["feature"], b["rate_s_h"])
            for a, b in zip(rates[:-1], rates[1:], strict=True)
        ]
        if not pairs:
            continue
        valid_x.append(pairs[-1][0])
        valid_feature.append(pairs[-1][1])
        valid_y.append(pairs[-1][2])
        train_x.extend(a for a, _, _ in pairs[:-1])
        train_feature.extend(feature for _, feature, _ in pairs[:-1])
        train_y.extend(b for _, _, b in pairs[:-1])
    if len(train_y) < 30 or len(valid_y) < 20:
        raise ValueError("insufficient strictly pre-target orbit history")
    affine = robust_affine(train_x, train_y)
    candidates = [
        {"name": "zero", "intercept_s_h": 0.0, "slope": 0.0},
        {"name": "median", "intercept_s_h": float(np.median(train_y)), "slope": 0.0},
        {"name": "persistence", "intercept_s_h": 0.0, "slope": 1.0},
        {"name": "robust_ar1", "intercept_s_h": float(affine[0]), "slope": float(affine[1])},
    ]
    candidates.extend(ridge_model(train_feature, train_y, alpha) for alpha in [0.1, 1, 10, 100])
    for model in candidates:
        error = np.asarray(
            [
                predict_rate(model, x, feature) - y
                for x, feature, y in zip(valid_x, valid_feature, valid_y, strict=True)
            ]
        )
        model["validation_median_absolute_rate_error_s_h"] = float(np.median(abs(error)))
        model["validation_rms_rate_error_s_h"] = rms(error)
    winning_candidate = select_candidate(candidates)
    winner_name = winning_candidate["name"]
    # Once the model class is chosen, use all pre-target transitions to estimate
    # its coefficients.  The target period still contributes no labels.
    all_x, all_feature, all_y = (
        train_x + valid_x,
        train_feature + valid_feature,
        train_y + valid_y,
    )
    winner = winning_candidate.copy()
    if winner_name == "median":
        winner["intercept_s_h"] = float(np.median(all_y))
    elif winner_name == "robust_ar1":
        coefficient = robust_affine(all_x, all_y)
        winner["intercept_s_h"], winner["slope"] = map(float, coefficient)
    elif winner_name == "ridge_features":
        winner = ridge_model(all_feature, all_y, winner["alpha"])
    return {
        "training_cutoff_utc_ns": cutoff_ns,
        "satellites_with_validation": len(valid_y),
        "historical_transitions": transition_count,
        "training_pairs": len(train_y),
        "validation_pairs": len(valid_y),
        "candidates": candidates,
        "winner": winner,
    }


def target_phase(row, records, model):
    cutoff = row["capture_start_utc_ns"]
    eligible = [
        item
        for item in records
        if item["epoch_utc_ns"] < cutoff and item["first_collected_utc_ns"] < cutoff
    ]
    current = next(
        (item for item in eligible if tle_key(item["text"]) == tle_key(row["winning_tle_text"])),
        None,
    )
    if current is None:
        raise ValueError(
            f"winning causal TLE absent from causal archive history: "
            f"{row['session_id']} NORAD {row['best_norad']}"
        )
    previous = [item for item in eligible if item["epoch_utc_ns"] < current["epoch_utc_ns"]]
    if not previous:
        return 0.0, None
    previous = max(
        previous, key=lambda item: (item["epoch_utc_ns"], item["first_collected_utc_ns"])
    )
    gap_h = (current["epoch_utc_ns"] - previous["epoch_utc_ns"]) / NS_HOUR
    if not 1 <= gap_h <= 72:
        return 0.0, None
    recent_phase = phase_seconds(previous["text"], current["text"], current["epoch_utc_ns"])
    recent_rate = recent_phase / gap_h
    old_sat = parse_element_sets(previous["text"]).satellites[0]
    new_sat = parse_element_sets(current["text"]).satellites[0]
    feature = [
        recent_rate,
        float(new_sat.bstar),
        float(new_sat.no_kozai),
        float(new_sat.ecco),
        float((new_sat.bstar - old_sat.bstar) / gap_h),
        float((new_sat.no_kozai - old_sat.no_kozai) / gap_h),
        float((new_sat.ecco - old_sat.ecco) / gap_h),
        gap_h,
    ]
    predicted_rate = predict_rate(model, recent_rate, feature)
    age_h = (row["capture_start_utc_ns"] - current["epoch_utc_ns"]) / NS_HOUR
    return predicted_rate * age_h, {
        "previous_epoch_utc_ns": previous["epoch_utc_ns"],
        "previous_first_collected_utc_ns": previous["first_collected_utc_ns"],
        "current_first_collected_utc_ns": current["first_collected_utc_ns"],
        "gap_h": gap_h,
        "recent_phase_s": recent_phase,
        "recent_rate_s_h": recent_rate,
        "predicted_rate_s_h": predicted_rate,
        "causal_age_h": age_h,
    }


def predicted_doppler(p, v, receiver):
    delta = p - receiver
    return -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * v, axis=1) / np.linalg.norm(delta, axis=1)


def replace_states(data, rows, phases):
    corrected = {key: value.copy() for key, value in data.items()}
    for index, (row, tau) in enumerate(zip(rows, phases, strict=True)):
        mask = data["episode"] == index
        times = data["time"][mask]
        cat = parse_element_sets(row["winning_tle_text"])
        for shift in [0.0, -0.5, 0.5]:
            p, v, valid = state_arrays(
                cat,
                [0],
                row["capture_start_utc_ns"],
                times,
                orbit_time_s=tau,
                clock_s=shift,
            )
            if len(valid) != 1:
                raise ValueError("invalid corrected target orbit")
            suffix = "" if shift == 0 else str(shift)
            corrected["p" + suffix][mask] = p[0]
            corrected["v" + suffix][mask] = v[0]
    return corrected


def rms_at_receiver(data, receiver):
    train = data["training"].astype(bool)
    residual = profile(
        data["y"] - predicted_doppler(data["p"], data["v"], receiver),
        data["segment"],
        train,
    )
    return rms(residual[~train])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ["archive-files", "causal", "retrospective", "parent", "output"]:
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".npz").exists():
        raise ValueError("fresh output required")
    causal_rows_raw = json.loads((args.causal / "strict-reranking.json").read_text())["rows"]
    retrospective_rows_raw = json.loads((args.retrospective / "full-reranking.json").read_text())[
        "rows"
    ]
    parent = json.loads((args.parent / "inference.json").read_text())
    keys = [(row["session_id"], row["episode_id"]) for row in parent["assignments"]]
    causal_lookup = {(row["session_id"], row["episode_id"]): row for row in causal_rows_raw}
    retrospective_lookup = {
        (row["session_id"], row["episode_id"]): row for row in retrospective_rows_raw
    }
    if set(keys) != set(causal_lookup) or set(keys) != set(retrospective_lookup):
        raise ValueError("orbit policy coverage mismatch")
    causal_rows = [causal_lookup[key] for key in keys]
    retrospective_rows = [retrospective_lookup[key] for key in keys]
    data = dict(np.load(args.causal / "strict-states.npz"))
    if len(causal_rows) != len(parent["assignments"]):
        raise ValueError("causal row coverage mismatch")
    wanted = {row["best_norad"] for row in causal_rows}
    histories = read_histories(
        args.archive_files.glob("*.tle"),
        wanted,
        max(row["capture_start_utc_ns"] for row in causal_rows),
    )
    cutoff = min(row["capture_start_utc_ns"] for row in causal_rows)
    frozen = freeze_model(histories, cutoff)
    phases, target_rows = [], []
    for row in causal_rows:
        phase, evidence = target_phase(row, histories[row["best_norad"]], frozen["winner"])
        phases.append(phase)
        target_rows.append(
            {
                "session_id": row["session_id"],
                "episode_id": row["episode_id"],
                "norad": row["best_norad"],
                "predicted_phase_s": phase,
                "history": evidence,
            }
        )
    corrected = replace_states(data, causal_rows, phases)
    causal_inference = json.loads((args.causal / "strict-inference.json").read_text())
    baseline = next(
        m
        for m in causal_inference["models"]
        if m["selection"] == "all" and m["clock_model"] == "fixed"
    )
    region = Region(**parent["region"])
    receiver = region.points([baseline["x_km"][0]], [baseline["x_km"][1]]).ecef_km[0]
    fixed_site = {
        "baseline_heldout_rms_hz": rms_at_receiver(data, receiver),
        "corrected_heldout_rms_hz": rms_at_receiver(corrected, receiver),
    }
    selected = [
        i for i, row in enumerate(parent["assignments"]) if row in parent["selected_assignments"]
    ]
    shared = next(
        m
        for m in causal_inference["models"]
        if m["selection"] == "all" and m["clock_model"] == "shared_recorded"
    )
    models = []
    for selection, mask in [
        ("all", np.ones(len(data["y"]), bool)),
        ("selected", np.isin(data["episode"], selected)),
    ]:
        for name, values in [("baseline", data), ("causal_phase_prior", corrected)]:
            for clock in ["fixed", "shared_recorded"]:
                result = fit(
                    values,
                    region,
                    parent["initial"],
                    "observation",
                    True,
                    subset=mask,
                    fit_clock=clock != "fixed",
                    clock_bounds={0: shared["clock_bounds_s"][0]} if clock != "fixed" else None,
                )
                models.append(
                    {"selection": selection, "orbit_model": name, "clock_model": clock, **result}
                )
                print(selection, name, clock, result["evaluation_rms_hz"], flush=True)
    # Later-TLE diagnostic on unchanged identities only.  It cannot influence
    # the frozen predictor, target phase, or fitted position.
    retro_lookup = {(row["session_id"], row["episode_id"]): row for row in retrospective_rows}
    train = data["training"].astype(bool)
    diagnostic = []
    oracle_phases = []
    for index, row in enumerate(causal_rows):
        newer = retro_lookup[(row["session_id"], row["episode_id"])]
        if (
            newer["best_norad"] != row["best_norad"]
            or newer["winning_tle_text"] == row["winning_tle_text"]
        ):
            oracle_phases.append(0.0)
            continue
        mask = data["episode"] == index
        oracle_tau = oracle_phase_seconds(
            row["winning_tle_text"],
            newer["winning_tle_text"],
            row["capture_start_utc_ns"],
            data["time"][mask],
        )
        oracle_phases.append(oracle_tau)
        future = parse_element_sets(newer["winning_tle_text"])
        p, v, valid = state_arrays(future, [0], row["capture_start_utc_ns"], data["time"][mask])
        if len(valid) != 1:
            continue
        future_hz = predicted_doppler(p[0], v[0], receiver)
        old_hz = predicted_doppler(data["p"][mask], data["v"][mask], receiver)
        corrected_hz = predicted_doppler(corrected["p"][mask], corrected["v"][mask], receiver)
        segment = data["segment"][mask]
        episode_train = train[mask]
        before = profile(future_hz - old_hz, segment, episode_train)
        after = profile(future_hz - corrected_hz, segment, episode_train)
        diagnostic.append(
            {
                "index": index,
                "predicted_phase_s": phases[index],
                "future_fitted_phase_s": oracle_tau,
                "baseline_future_tle_mismatch_hz": rms(before[~episode_train]),
                "corrected_future_tle_mismatch_hz": rms(after[~episode_train]),
            }
        )
    oracle_corrected = replace_states(data, causal_rows, oracle_phases)
    for selection, mask in [
        ("all", np.ones(len(data["y"]), bool)),
        ("selected", np.isin(data["episode"], selected)),
    ]:
        for clock in ["fixed", "shared_recorded"]:
            result = fit(
                oracle_corrected,
                region,
                parent["initial"],
                "observation",
                True,
                subset=mask,
                fit_clock=clock != "fixed",
                clock_bounds={0: shared["clock_bounds_s"][0]} if clock != "fixed" else None,
            )
            models.append(
                {
                    "selection": selection,
                    "orbit_model": "future_tle_oracle_phase",
                    "clock_model": clock,
                    **result,
                }
            )
            print(
                selection,
                "future_tle_oracle_phase",
                clock,
                result["evaluation_rms_hz"],
                flush=True,
            )
    output = {
        "strictly_causal": True,
        "evaluation_location_used": False,
        "future_tles_used_to_choose_model": False,
        "future_tles_used_for_labelled_diagnostic_only": True,
        "causal_digest": digest(args.causal / "strict-inference.json"),
        "parent_digest": digest(args.parent / "inference.json"),
        "archive_file_count": len(list(args.archive_files.glob("*.tle"))),
        "historical_population_policy": (
            "satellite IDs selected by the strict-causal target reranking; "
            "history remains independently cut off before each capture"
        ),
        "historical_population_satellites": len(wanted),
        "frozen_model": frozen,
        "target_phase_summary": {
            "count": len(phases),
            "targets_without_usable_predecessor": sum(
                row["history"] is None for row in target_rows
            ),
            "median_s": float(np.median(phases)),
            "p05_s": float(np.quantile(phases, 0.05)),
            "p95_s": float(np.quantile(phases, 0.95)),
            "min_s": min(phases),
            "max_s": max(phases),
        },
        "fixed_causal_receiver": fixed_site,
        "models": models,
        "targets": target_rows,
        "future_tle_diagnostic": diagnostic,
    }
    np.savez_compressed(args.output.with_suffix(".npz"), **corrected)
    output["states_digest"] = digest(args.output.with_suffix(".npz"))
    write_json(args.output, output)


if __name__ == "__main__":
    main()
