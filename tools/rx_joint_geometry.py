"""Joint geometry experiment with a frozen empirical observational reference."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from tools.rx_empirical_background import log_density
from tools.rx_empirical_signal import paired_relative_log_likelihood
from tools.rx_geometry_fit import raw_features
from tools.rx_geometry_frozen_score import validate_frozen_model
from tools.rx_geometry_likelihood import periodic_signal_ratio
from tools.rx_joint_geometry_fit import fit_arms
from tools.rx_presence_filter import forward_score
from tools.rx_presence_geometry import posterior_summary, prepare_lanes

ARMS = ("D", "E", "S", "T")


def attach_reference(
    lanes, background, sigma, *, calibration_only=False, control=None, center=None, scale=None
):
    if background.get("mode") != "joint":
        raise ValueError("this experiment requires the frozen joint/uniform reference")
    output = []
    for lane in lanes:
        source = lane["source"]
        if calibration_only and source["recording_split"] != "calibration":
            continue
        indices = [
            i
            for i, window in enumerate(source["windows"])
            if not calibration_only or window["role"] == "reception"
        ]
        period = source["alias_period_hz"]
        x = lane["x"]
        if control in ("swap", "reverse"):
            x = (raw_features(source, control)[0] - center) / scale
        x = x[indices, :-1]
        mu = lane["mu"][indices, :-1].copy()
        if control == "shift":
            mu += period / 4
        counts = lane["counts"][indices]
        signal = np.zeros((*mu.shape, 2))
        count_logs = np.full((len(indices), 2, 2), -np.inf)
        reference = []
        for i, index in enumerate(indices):
            window = source["windows"][index]
            observed = [
                [candidate["canonical_rx0_hz"] for candidate in window["observed"][rx]]
                for rx in ("rx0", "rx1")
            ]
            row = {
                "counts": counts[i].tolist(),
                "rate_hz": window["sample_rate_hz"],
                "frequencies": [
                    [float(value % period / period) for value in values] for values in observed
                ],
            }
            reference.append(log_density(background, row) - sum(row["counts"]) * math.log(period))
            for s0 in (0, 1):
                for s1 in (0, 1):
                    shifted = [row["counts"][0] - s0, row["counts"][1] - s1]
                    if min(shifted) < 0:
                        continue
                    synthetic = {
                        "counts": shifted,
                        "rate_hz": row["rate_hz"],
                        "frequencies": [[0.0] * n for n in shifted],
                    }
                    count_logs[i, s0, s1] = log_density(background, synthetic) - sum(
                        math.lgamma(n + 1) for n in shifted
                    )
            for rid in range(2):
                signal[i, :, rid] = periodic_signal_ratio(observed[rid], mu[i], period, sigma)
        output.append(
            {
                "source": source,
                "indices": indices,
                "x": x,
                "visible": lane["visible"][indices, :-1],
                "counts": counts,
                "signal": signal,
                "log_count_probabilities": count_logs,
                "reference": np.array(reference),
                "prior": lane["prior"],
                "times": lane["times"][indices],
                "roles": lane["roles"][indices],
            }
        )
    return output


def relative_emissions(lane, beta):
    relative = paired_relative_log_likelihood(
        lane["log_count_probabilities"],
        lane["signal"],
        lane["counts"],
        lane["x"][..., : len(beta)] @ beta,
        lane["visible"],
    )
    return np.column_stack((np.zeros(len(relative)), relative))


def evaluate(lanes, fitted):
    records, exports = {}, []
    for lane in lanes:
        if lane["source"]["recording_split"] != "evaluation":
            continue
        emission = relative_emissions(lane, np.array(fitted["beta"]))
        rec = lane["roles"] == "reception"
        held = lane["roles"] == "held_frequency"
        score = forward_score(
            lane["prior"], emission, lane["times"], rec, held, fitted["occupancy"], fitted["tau_s"]
        )
        sid = lane["source"]["lane"]["session_id"]
        record = records.setdefault(
            sid, {"held_windows": 0, "relative_log_score": 0.0, "reference_log_score": 0.0}
        )
        record["held_windows"] += int(held.sum())
        record["relative_log_score"] += float(score.window_log_scores[held].sum())
        record["reference_log_score"] += float(lane["reference"][held].sum())
        exports.append(
            {
                "lane": lane["source"]["lane"],
                "components": lane["source"]["components"][:-1],
                "held_window_ids": [
                    lane["source"]["windows"][i]["source_window_id"]
                    for i, is_held in zip(lane["indices"], held, strict=True)
                    if is_held
                ],
                "held_relative_scores": score.window_log_scores[held].tolist(),
                "reception_posterior": posterior_summary(score.reception_log_posterior),
                "held_posterior": posterior_summary(score.held_log_posterior),
                "window_presence": score.posterior_presence.tolist(),
            }
        )
    if not records:
        raise ValueError("empty evaluation population")
    for record in records.values():
        record["versus_reference_per_window"] = (
            record["relative_log_score"] / record["held_windows"]
        )
        record["full_log_score"] = record["reference_log_score"] + record["relative_log_score"]
    return {
        "records": records,
        "lanes": exports,
        "mean_vs_reference": float(
            np.mean([r["versus_reference_per_window"] for r in records.values()])
        ),
    }


def run(pilot, confirmation, old_model, background_result):
    center, scale, _ = validate_frozen_model(old_model)
    if (
        background_result.get("schema") != "rx-empirical-background-selection/v1"
        or background_result.get("status") != "complete"
        or background_result.get("selected_mode") != "joint"
    ):
        raise ValueError("reference selection must be complete and select joint counts")
    background = background_result["selected_model"]
    if (
        background.get("schema") != "rx-empirical-background/v1"
        or background.get("mode") != background_result["selected_mode"]
        or not isinstance(background.get("rows"), int)
    ):
        raise ValueError("invalid selected reference model")
    pids = {lane["lane"]["session_id"] for lane in pilot["lanes"]}
    cids = {lane["lane"]["session_id"] for lane in confirmation["lanes"]}
    if pids & cids or any(
        lane["recording_split"] != "evaluation" for lane in confirmation["lanes"]
    ):
        raise ValueError("confirmation must be disjoint and evaluation-only")
    pilot_lanes = prepare_lanes(pilot, center, scale)
    training = attach_reference(
        pilot_lanes, background, old_model["sigma_hz"], calibration_only=True
    )
    if len({lane["source"]["lane"]["session_id"] for lane in training}) != 6:
        raise ValueError("calibration population must contain six records")
    if sum(len(lane["times"]) for lane in training) != background["rows"]:
        raise ValueError("reference/calibration population mismatch")
    if {lane["source"]["lane"]["session_id"] for lane in training} != set(
        background_result["calibration_recordings"]
    ):
        raise ValueError("reference/calibration recording membership mismatch")
    fit_result = fit_arms(training, old_model["fits"])
    fits = {arm: value["selected"] for arm, value in fit_result["fits"].items()}
    panels = {}
    for name, lanes in (
        ("pilot", pilot_lanes),
        ("confirmation", prepare_lanes(confirmation, center, scale)),
    ):
        prepared = attach_reference(lanes, background, old_model["sigma_hz"])
        evaluations = {arm: evaluate(prepared, fits[arm]) for arm in ARMS}
        for control in ("swap", "reverse", "shift"):
            modified = attach_reference(
                lanes,
                background,
                old_model["sigma_hz"],
                control=control,
                center=center,
                scale=scale,
            )
            for arm in ARMS if control == "shift" else ("T",):
                evaluations[arm + "_" + control] = evaluate(modified, fits[arm])
        denominators = [
            {sid: r["held_windows"] for sid, r in e["records"].items()}
            for e in evaluations.values()
        ]
        if any(value != denominators[0] for value in denominators):
            raise ValueError("control denominators disagree")
        contrasts = {}
        for left, right in (
            ("E", "D"),
            ("S", "D"),
            ("S", "E"),
            ("T", "S"),
            ("T", "T_swap"),
            ("T", "T_reverse"),
            *((arm, arm + "_shift") for arm in ARMS),
        ):
            values = {
                sid: evaluations[left]["records"][sid]["versus_reference_per_window"]
                - evaluations[right]["records"][sid]["versus_reference_per_window"]
                for sid in evaluations[left]["records"]
            }
            contrasts[left + "-" + right] = {
                "records": values,
                "mean": float(np.mean(list(values.values()))),
            }
        panels[name] = {"evaluations": evaluations, "contrasts": contrasts}
    combined = {}
    for arm in ARMS:
        values = {
            sid: row["versus_reference_per_window"]
            for panel in panels.values()
            for sid, row in panel["evaluations"][arm]["records"].items()
        }
        combined[arm + "-reference"] = {
            "records": values,
            "mean": float(np.mean(list(values.values()))),
            "positive_records": sum(value > 0 for value in values.values()),
        }
    for contrast in panels["pilot"]["contrasts"]:
        values = {
            sid: value
            for panel in panels.values()
            for sid, value in panel["contrasts"][contrast]["records"].items()
        }
        combined[contrast] = {
            "records": values,
            "mean": float(np.mean(list(values.values()))),
            "positive_records": sum(value > 0 for value in values.values()),
        }
    if any(len(value["records"]) != 8 for value in combined.values()):
        raise ValueError("expected eight distinct evaluation recordings")
    return {
        "schema": "rx-joint-geometry/v1",
        "status": "complete",
        "fits": fit_result["fits"],
        "panels": panels,
        "combined_equal_record": combined,
        "background_mode": background["mode"],
        "interpretation": "Reused-panel joint refit with frozen mixed observational reference.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pilot", "confirmation", "old-model", "background", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    paths = {
        key: getattr(args, key) for key in ("pilot", "confirmation", "old_model", "background")
    }
    payloads = {key: path.read_bytes() for key, path in paths.items()}
    documents = {key: json.loads(payload) for key, payload in payloads.items()}
    digest = hashlib.sha256(payloads["pilot"]).hexdigest()
    if (
        digest != documents["old_model"]["dataset_sha256"]
        or digest != documents["background"]["dataset_sha256"]
    ):
        raise ValueError("frozen model/reference dataset digest mismatch")
    if args.output.exists():
        raise FileExistsError(args.output)
    result = run(
        documents["pilot"],
        documents["confirmation"],
        documents["old_model"],
        documents["background"],
    )
    result["source_sha256"] = {
        key: hashlib.sha256(payload).hexdigest() for key, payload in payloads.items()
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
