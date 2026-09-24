"""Test calibration-phase diagnostics as CFO uncertainty indicators."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
BASE_PATH = ROOT / "tools/research/evaluate_longarc_phase.py"
SPEC = importlib.util.spec_from_file_location("longarc_base", BASE_PATH)
BASE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BASE)

import replay_regional_doppler as replay  # noqa: E402

from leo.analysis.research.formal_orbit import doppler_hz  # noqa: E402
from leo.sky.frames import geodetic_to_ecef_km  # noqa: E402
from leo.sky.propagation import parse_element_sets  # noqa: E402

FIGURE = ROOT / "reports/figures/2026_09_23_longarc_phase"
ORBIT = ROOT / "reports/artifacts/2026_09_21_shared_identity_orbit"
SEED = 20260923
GOOD_SIGMA_HZ = 250.0


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_nll(residual: np.ndarray, sigma_hz: float) -> float:
    residual = np.asarray(residual, float)
    if len(residual) == 0 or not np.isfinite(sigma_hz) or sigma_hz <= 0:
        raise ValueError("finite residuals and positive scale required")
    return float(
        np.mean(0.5 * (residual / sigma_hz) ** 2 + np.log(sigma_hz) + 0.5 * np.log(2 * np.pi))
    )


def stratified_random_folds(strata: np.ndarray, eligible: np.ndarray, folds: int = 3) -> np.ndarray:
    """Assign seeded random folds independently inside every temporal stratum."""
    strata, eligible = np.asarray(strata), np.asarray(eligible, bool)
    result = np.full(len(strata), -1, dtype=int)
    rng = np.random.default_rng(SEED)
    for stratum in np.unique(strata[eligible]):
        indices = np.flatnonzero(eligible & (strata == stratum))
        result[indices] = np.arange(len(indices))[rng.permutation(len(indices))] % folds
    return result


def calibration_features(row: dict) -> dict:
    branch = row["branches"][row["selected_seed_index"]]
    frames = [
        item
        for item in branch["frames"]
        if item["group_id"] in (0, 3, 5)
        and item["frame"]["training_supported"]
        and item["frame"]["even"] is not None
        and not item["frame"]["even"]["search_boundary"]
    ]
    if len(frames) < 6:
        raise ValueError("insufficient calibration-even frames")
    cfo = np.asarray([item["frame"]["even"]["absolute_cfo_hz"] for item in frames])
    time = np.asarray([item["session_time_s"] for item in frames])
    design = np.column_stack([np.ones(len(time)), time - time.mean()])
    cfo_scatter = float(np.std(cfo - design @ np.linalg.lstsq(design, cfo, rcond=None)[0]))
    group_resultants = []
    for group in (0, 3, 5):
        selected = sorted(
            [item for item in frames if item["group_id"] == group],
            key=lambda item: item["session_time_s"],
        )
        phasors = []
        for left, right in zip(selected[:-1], selected[1:], strict=True):
            lv = np.asarray(left["frame"]["even"]["channel_vector"])
            rv = np.asarray(right["frame"]["even"]["channel_vector"])
            lv = lv[:, 0] + 1j * lv[:, 1]
            rv = rv[:, 0] + 1j * rv[:, 1]
            measured = np.angle(np.vdot(lv, rv))
            dt = right["session_time_s"] - left["session_time_s"]
            frequency = 0.5 * (
                left["frame"]["even"]["absolute_cfo_hz"] + right["frame"]["even"]["absolute_cfo_hz"]
            )
            phasors.append(np.exp(2j * (measured - 2 * np.pi * frequency * dt)))
        if phasors:
            group_resultants.append(abs(np.mean(phasors)))
    if not group_resultants:
        raise ValueError("no complete calibration phase increments")
    return {
        "phase_resultant": float(np.mean(group_resultants)),
        "cfo_scatter_hz": cfo_scatter,
        "rolled_control_coherence": float(
            np.mean([item["frame"]["even"]["control_coherence"] for item in frames])
        ),
        "phase_group_count": len(group_resultants),
    }


def select_config(
    residuals: list[np.ndarray],
    feature: np.ndarray,
    folds: np.ndarray,
    thresholds: tuple[float, ...],
) -> dict:
    candidates = []
    for threshold in thresholds:
        for good_sigma in (150.0, 250.0, 500.0, 1000.0):
            for bad_sigma in (150.0, 250.0, 500.0, 1000.0):
                if bad_sigma < good_sigma:
                    continue
                scores = []
                for fold in sorted(set(folds[folds >= 0])):
                    indices = np.flatnonzero(folds == fold)
                    scores.extend(
                        normalized_nll(
                            residuals[index],
                            bad_sigma if feature[index] < threshold else good_sigma,
                        )
                        for index in indices
                    )
                candidates.append((float(np.mean(scores)), threshold, good_sigma, bad_sigma))
    score, threshold, good_sigma, bad_sigma = min(candidates)
    return {
        "inner_nll": score,
        "threshold": threshold,
        "good_sigma_hz": good_sigma,
        "bad_sigma_hz": bad_sigma,
    }


def main() -> None:
    binding = json.loads((FIGURE / "binding.json").read_text())
    with gzip.open(FIGURE / "replay/frames.json.gz", "rt") as stream:
        replayed = json.load(stream)
    evaluation = json.loads((FIGURE / "evaluation.json").read_text())
    if replayed["protocol"]["binding_sha256"] != digest(FIGURE / "binding.json"):
        raise ValueError("replay binding digest changed")
    for relative, expected in evaluation["input_sha256"].items():
        if digest(ROOT / relative) != expected:
            raise ValueError(f"primary evaluation input changed: {relative}")
    rows = sorted(replayed["rows"], key=lambda row: row["observation"]["time_s"])
    times = np.asarray([row["observation"]["time_s"] for row in rows])
    training = np.asarray([row["outer_partition"] == "train" for row in rows])
    split = {
        row["visit_index"]: row for row in binding["phase_random_whole_visit_partition"]["rows"]
    }
    strata = np.asarray(
        [split[row["observation"]["visit_index"]]["temporal_stratum"] for row in rows]
    )
    folds = stratified_random_folds(strata, training)
    features = [calibration_features(row) for row in rows]

    index = binding["episode_cache_index"]
    with np.load(ORBIT / "candidate-phase-states.npz", allow_pickle=False) as archive:
        norad = archive[f"norad_{index}"].astype(int)
    with gzip.open(ORBIT / "audit.retained-tles.json.gz", "rt") as stream:
        records = json.load(stream)[binding["session_id"]]["records"]
    catalogue = parse_element_sets("".join(records[str(value)] for value in norad))
    fit = next(
        row
        for row in json.loads((ORBIT / "fit.json").read_text())["models"]
        if row["identity_model"] == "joint_candidate_mixture"
    )
    receiver = geodetic_to_ecef_km(fit["latitude_deg"], fit["longitude_deg"], 0.0)
    reference_ns = binding["historical_inventory"]["reference_utc_ns"]
    p, v, valid = replay.state_arrays(catalogue, list(range(len(norad))), reference_ns, times)
    if not np.array_equal(valid, np.arange(len(norad))):
        raise ValueError("candidate propagation failed")
    predicted = doppler_hz(receiver, p, v)
    glrt = np.asarray([row["observation"]["normalized_cfo_hz"] for row in rows])

    responses, response_times = [], []
    for row in rows:
        observation = row["observation"]
        branch = row["branches"][row["selected_seed_index"]]
        selected = [
            item
            for item in branch["frames"]
            if item["group_id"] in (1, 2, 4)
            and item["frame"]["training_supported"]
            and item["frame"]["odd"] is not None
        ]
        responses.append(
            np.asarray(
                [
                    BASE.normalized_frame_cfo(item, observation, "odd", reject_boundary=False)
                    for item in selected
                ]
            )
        )
        response_times.append(np.asarray([item["session_time_s"] for item in selected]))

    def residual_for(model: dict, row_index: int) -> np.ndarray:
        p_, v_, valid_ = replay.state_arrays(
            catalogue, list(range(len(norad))), reference_ns, response_times[row_index]
        )
        if not np.array_equal(valid_, np.arange(len(norad))):
            raise ValueError("response propagation failed")
        prediction = BASE.predict_selected(
            model, doppler_hz(receiver, p_, v_), response_times[row_index]
        )
        return responses[row_index] - prediction

    cross_residuals = [np.asarray([]) for _ in rows]
    for fold in range(3):
        inner_training = training & (folds != fold)
        model = BASE.fit_candidate_affine(glrt, predicted, times, inner_training)
        for row_index in np.flatnonzero(folds == fold):
            cross_residuals[row_index] = residual_for(model, row_index)

    phase = np.asarray([row["phase_resultant"] for row in features])
    scatter = np.asarray([row["cfo_scatter_hz"] for row in features])
    control = np.asarray([row["rolled_control_coherence"] for row in features])
    rng = np.random.default_rng(SEED + 1)
    permuted = phase.copy()
    for stratum in np.unique(strata):
        for partition in (False, True):
            indices = np.flatnonzero((strata == stratum) & (training == partition))
            permuted[indices] = phase[indices][rng.permutation(len(indices))]
    # Lower values always mean less reliable for the shared selector.
    covariates = {
        "phase_resultant": (phase, (0.8, 0.9, 0.95)),
        "even_cfo_scatter": (-scatter, (-200.0, -150.0, -100.0)),
        "rolled_control": (-control, (-0.014, -0.011, -0.008)),
        "phase_permuted_within_stratum": (permuted, (0.8, 0.9, 0.95)),
    }
    configs = {
        name: select_config(cross_residuals, values, folds, thresholds)
        for name, (values, thresholds) in covariates.items()
    }
    uniform_candidates = [
        (
            float(
                np.mean(
                    [
                        normalized_nll(cross_residuals[index], sigma)
                        for index in np.flatnonzero(training)
                    ]
                )
            ),
            sigma,
        )
        for sigma in (150.0, 250.0, 500.0, 1000.0)
    ]
    uniform_inner_nll, uniform_sigma = min(uniform_candidates)
    final_model = evaluation["glrt_model"]
    held = np.flatnonzero(~training)
    held_residuals = [residual_for(final_model, index_) for index_ in held]
    baseline_nll = float(np.mean([normalized_nll(row, uniform_sigma) for row in held_residuals]))
    results, held_nll = {}, {}
    held_nll["uniform"] = [normalized_nll(row, uniform_sigma) for row in held_residuals]
    for name, (values, _) in covariates.items():
        config = configs[name]
        flagged = values[held] < config["threshold"]
        nll = [
            normalized_nll(row, config["bad_sigma_hz"] if flag else config["good_sigma_hz"])
            for row, flag in zip(held_residuals, flagged, strict=True)
        ]
        rms = np.asarray([np.sqrt(np.mean(row**2)) for row in held_residuals])
        results[name] = {
            **config,
            "held_nll": float(np.mean(nll)),
            "held_nll_gain_vs_uniform": baseline_nll - float(np.mean(nll)),
            "held_flagged_visits": int(flagged.sum()),
            "held_flagged_rms_hz": (
                float(np.sqrt(np.mean(rms[flagged] ** 2))) if flagged.any() else None
            ),
            "held_unflagged_rms_hz": (
                float(np.sqrt(np.mean(rms[~flagged] ** 2))) if (~flagged).any() else None
            ),
        }
        held_nll[name] = nll
    output = {
        "schema": "longarc-phase-reliability/v1",
        "outer_split": {"train": int(training.sum()), "held": int((~training).sum())},
        "inner_split": "seeded random 3-fold assignment within each temporal stratum",
        "held_visits_all_scored": len(held_residuals) == int((~training).sum()),
        "phase_calibration_group_coverage": {
            "minimum": min(row["phase_group_count"] for row in features),
            "maximum": max(row["phase_group_count"] for row in features),
            "all_three_groups": sum(row["phase_group_count"] == 3 for row in features),
        },
        "uniform_model": {
            "inner_nll": uniform_inner_nll,
            "sigma_hz": uniform_sigma,
            "held_nll": baseline_nll,
            "held_rms_hz": BASE.equal_visit_rms(held_residuals),
        },
        "results": results,
        "configuration_selected_without_outer_held": True,
        "interpretation": (
            "reliability-screen diagnostic on a fixed GLRT candidate/nuisance model; "
            "not a weighted association improvement"
        ),
        "input_sha256": {
            str(path.relative_to(ROOT)): digest(path)
            for path in (
                FIGURE / "binding.json",
                FIGURE / "replay/frames.json.gz",
                FIGURE / "evaluation.json",
                ORBIT / "candidate-phase-states.npz",
                ORBIT / "audit.retained-tles.json.gz",
                ORBIT / "fit.json",
            )
        },
        "source_sha256": digest(Path(__file__)),
        "visits": [
            {
                "visit_index": row["observation"]["visit_index"],
                "time_s": row["observation"]["time_s"],
                "temporal_stratum": int(strata[index_]),
                "outer_partition": row["outer_partition"],
                "inner_fold": int(folds[index_]),
                **features[index_],
                **(
                    {
                        "held_nll": {
                            name: float(values[list(held).index(index_)])
                            for name, values in held_nll.items()
                        }
                    }
                    if not training[index_]
                    else {}
                ),
            }
            for index_, row in enumerate(rows)
        ],
    }
    target = FIGURE / "reliability.json"
    target.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
