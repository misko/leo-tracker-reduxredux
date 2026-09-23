"""Conditional circular phase-rate comparison on random whole-visit holdouts.

Frame pairs never cross a 20 ms group or a retune. One phase-advance intercept
per visit uses only its calibration-even frames; one common rate per candidate
uses only outer training visits. This is not an absolute phase/orbit solution.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np

from tools.research import evaluate_longarc_phase as cfo


def pair_rows(row, groups, fold):
    branch = row["branches"][row["selected_seed_index"]]
    output = []
    for group in groups:
        frames = sorted(
            [frame for frame in branch["frames"] if frame["group_id"] == group],
            key=lambda frame: frame["session_time_s"],
        )
        if len(frames) != 4:
            raise ValueError("expected four fixed frame opportunities per group")
        for left, right in ((frames[0], frames[1]), (frames[2], frames[3])):
            # Eligibility uses the pre-existing even-symbol support, never odd fit quality.
            if not all(frame["frame"]["training_supported"] for frame in (left, right)):
                continue
            if any(frame["frame"][fold] is None for frame in (left, right)):
                continue
            vectors = []
            for frame in (left, right):
                values = np.asarray(frame["frame"][fold]["channel_vector"])
                vectors.append(values[:, 0] + 1j * values[:, 1])
            cross = np.vdot(vectors[0], vectors[1])
            if abs(cross) == 0:
                raise ValueError("zero complex phase response; do not silently gate held data")
            duration = right["session_time_s"] - left["session_time_s"]
            if not np.isclose(duration, 1 / 750, rtol=0, atol=1e-12):
                raise ValueError("analytic phase intercept requires equal adjacent-frame spacing")
            output.append(
                {
                    "group": group,
                    "midpoint_s": (left["session_time_s"] + right["session_time_s"]) / 2,
                    "duration_s": duration,
                    "phase_rad": float(np.angle(cross)),
                    "endpoint_ids": [
                        f"{row['observation']['visit_index']}:{frame['frame']['frame_start_sample']}"
                        for frame in (left, right)
                    ],
                }
            )
    return output


def group_weights(pairs):
    groups = np.asarray([pair["group"] for pair in pairs])
    unique = np.unique(groups)
    return np.asarray([1 / (len(unique) * np.sum(groups == group)) for group in groups])


def fit_and_score(calibration, response, training, rate_grid):
    """Select candidate/rate with outer-train even inputs; score untouched odd inputs.

    Each item carries measured phase, candidate predictions, within-visit rate
    phase coefficients, and equal-group weights. Calibration on a held visit is
    an explicit conditioning input. The response never influences fitted values.
    """
    training = np.asarray(training, bool)
    if len(calibration) != len(response) or len(training) != len(calibration):
        raise ValueError("visit population differs between arms")
    candidates = calibration[0]["prediction"].shape[0]
    models = []
    for candidate in range(candidates):
        scores, shifts = [], []
        for row in calibration:
            residual = (
                row["measured"][None, :]
                - row["prediction"][candidate][None, :]
                - rate_grid[:, None] * row["rate_phase"][None, :]
            )
            moment = np.sum(row["weights"] * np.exp(2j * residual), axis=1)
            shifts.append(np.angle(moment) / 2)
            scores.append(np.abs(moment))
        scores = np.asarray(scores)
        choice = int(np.argmax(np.mean(scores[training], axis=0)))
        held_scores, held_rms = [], []
        for index, row in enumerate(response):
            residual = (
                row["measured"]
                - row["prediction"][candidate]
                - rate_grid[choice] * row["rate_phase"]
                - shifts[index][choice]
            )
            wrapped = (residual + np.pi / 2) % np.pi - np.pi / 2
            held_scores.append(float(np.sum(row["weights"] * np.cos(2 * residual))))
            held_rms.append(float(np.sum(row["weights"] * wrapped**2)))
        models.append(
            {
                "rate_hz_s": float(rate_grid[choice]),
                "rate_grid_boundary": choice in (0, len(rate_grid) - 1),
                "training_score": float(np.mean(scores[training, choice])),
                "held_score": float(np.mean(np.asarray(held_scores)[~training])),
                "held_rms_rad": float(np.sqrt(np.mean(np.asarray(held_rms)[~training]))),
                "held_visit_scores": np.asarray(held_scores)[~training].tolist(),
            }
        )
    return models


def paired_bootstrap(left, right, seed=20260924):
    difference = np.asarray(left) - np.asarray(right)
    indexes = np.random.default_rng(seed).integers(0, len(difference), (4000, len(difference)))
    return {
        "mean_score_gain": float(np.mean(difference)),
        "percentile_95_interval": np.quantile(
            np.mean(difference[indexes], axis=1), [0.025, 0.975]
        ).tolist(),
        "seed": seed,
        "replicates": 4000,
        "unit": "paired whole held visit; descriptive, temporally correlated visits possible",
    }


def main():
    binding_path = cfo.FIGURE / "binding.json"
    frames_path = cfo.FIGURE / "replay/frames.json.gz"
    binding = json.loads(binding_path.read_text())
    with gzip.open(frames_path, "rt") as stream:
        replayed = json.load(stream)
    if replayed["protocol"]["binding_sha256"] != cfo.digest(binding_path):
        raise ValueError("replay binding digest changed")
    primary = json.loads((cfo.FIGURE / "evaluation.json").read_text())
    # Reuse only the validated candidate identities and frozen RF-derived location.
    for name, expected in primary["input_sha256"].items():
        if cfo.digest(cfo.ROOT / name) != expected:
            raise ValueError(f"primary comparison input changed: {name}")
    norad = primary["candidate_norad"]
    with gzip.open(cfo.ORBIT / "audit.retained-tles.json.gz", "rt") as stream:
        records = json.load(stream)[binding["session_id"]]["records"]
    catalogue = cfo.parse_element_sets("".join(records[str(value)] for value in norad))
    reference = primary["receiver_reference"]
    receiver = cfo.geodetic_to_ecef_km(reference["latitude_deg"], reference["longitude_deg"], 0)
    calibration, response, training, visits, excluded = [], [], [], [], []
    wrong_calibration, wrong_response = [], []
    bound_times = [row["observation"]["time_s"] for row in replayed["rows"]]
    mirror_sum = min(bound_times) + max(bound_times)
    for row in replayed["rows"]:
        even = pair_rows(row, [0, 3, 5], "even")
        odd = pair_rows(row, [1, 2, 4], "odd")
        if len({pair["group"] for pair in even}) < 2 or not odd:
            excluded.append(row["observation"]["visit_index"])
            continue
        even_ids = {value for pair in even for value in pair["endpoint_ids"]}
        odd_ids = {value for pair in odd for value in pair["endpoint_ids"]}
        if even_ids & odd_ids:
            raise ValueError("physical frame endpoint crosses inner split")
        origin = float(np.mean([pair["midpoint_s"] for pair in even]))
        scale = row["observation"]["historical_rf_normalization_scale"]
        for pairs, target, wrong_target in (
            (even, calibration, wrong_calibration),
            (odd, response, wrong_response),
        ):
            times = np.asarray([pair["midpoint_s"] for pair in pairs])
            duration = np.asarray([pair["duration_s"] for pair in pairs])
            p, v, valid = cfo.replay.state_arrays(
                catalogue,
                list(range(len(norad))),
                binding["historical_inventory"]["reference_utc_ns"],
                times,
            )
            if not np.array_equal(valid, np.arange(len(norad))):
                raise ValueError("phase midpoint propagation failed")
            phase = 2 * np.pi * cfo.doppler_hz(receiver, p, v) / scale * duration
            target.append(
                {
                    "measured": np.asarray([pair["phase_rad"] for pair in pairs]),
                    "prediction": np.vstack([np.zeros(len(pairs)), phase]),
                    "rate_phase": 2 * np.pi * (times - origin) * duration,
                    "weights": group_weights(pairs),
                }
            )
            # Reverse visit locations along the arc while preserving local time direction.
            # This is a geometry control, not a chronological validation split.
            visit_time = row["observation"]["time_s"]
            wrong_times = mirror_sum - visit_time + (times - visit_time)
            wp, wv, wvalid = cfo.replay.state_arrays(
                catalogue,
                list(range(len(norad))),
                binding["historical_inventory"]["reference_utc_ns"],
                wrong_times,
            )
            if not np.array_equal(wvalid, np.arange(len(norad))):
                raise ValueError("wrong-time control propagation failed")
            wrong_phase = 2 * np.pi * cfo.doppler_hz(receiver, wp, wv) / scale * duration
            wrong_target.append({**target[-1], "prediction": wrong_phase})
        training.append(row["outer_partition"] == "train")
        visits.append(
            {
                "visit_index": row["observation"]["visit_index"],
                "partition": row["outer_partition"],
                "even_pairs": len(even),
                "odd_pairs": len(odd),
            }
        )
    models = fit_and_score(calibration, response, training, np.linspace(-5000, 5000, 401))
    for identity, model in zip(["constant_rate_control", *norad], models, strict=True):
        model["candidate"] = identity
    winner = 1 + int(np.argmax([model["training_score"] for model in models[1:]]))
    wrong_models = fit_and_score(
        wrong_calibration, wrong_response, training, np.linspace(-5000, 5000, 401)
    )
    for identity, model in zip(norad, wrong_models, strict=True):
        model["candidate"] = identity
    wrong_winner = int(np.argmax([model["training_score"] for model in wrong_models]))
    output = {
        "schema": "conditional-longarc-phase-advance/v1",
        "scope": "retrospective conditional phase-rate experiment; no identity or position claim",
        "phase_period_rad": float(np.pi),
        "phase_integral": "native RF Doppler midpoint rule on disjoint adjacent 1/750s pairs",
        "nuisance": (
            "one local advance intercept from calibration even frames per visit; "
            "one global rate per candidate from outer training visits"
        ),
        "outer_seed": binding["seed"],
        "outer_train_visits": sum(training),
        "outer_held_visits": len(training) - sum(training),
        "held_response_used_for_fitting": False,
        "fractional_timing_corrected": False,
        "training_selected_candidate": models[winner]["candidate"],
        "selected_vs_constant_rate": paired_bootstrap(
            models[winner]["held_visit_scores"], models[0]["held_visit_scores"]
        ),
        "wrong_time_training_selected_candidate": wrong_models[wrong_winner]["candidate"],
        "selected_vs_wrong_time": paired_bootstrap(
            models[winner]["held_visit_scores"], wrong_models[wrong_winner]["held_visit_scores"]
        ),
        "wrong_time_models": wrong_models,
        "models": models,
        "coverage": visits,
        "excluded_visits": excluded,
        "input_sha256": {
            str(path.relative_to(cfo.ROOT)): cfo.digest(path)
            for path in (binding_path, frames_path, cfo.FIGURE / "evaluation.json")
        },
        "source_sha256": cfo.digest(Path(__file__)),
    }
    (cfo.FIGURE / "phase-advances.json").write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: output[key]
                for key in (
                    "outer_train_visits",
                    "outer_held_visits",
                    "training_selected_candidate",
                    "excluded_visits",
                )
            }
        )
    )
    for model in models:
        print({key: value for key, value in model.items() if key != "held_visit_scores"})


if __name__ == "__main__":
    main()
