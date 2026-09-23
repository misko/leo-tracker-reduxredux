"""Evaluate source-pilot CFO against archived GLRT on frozen long-arc groups."""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import replay_regional_doppler as replay  # noqa: E402

import leo.analysis.research.formal_orbit as formal_orbit_module  # noqa: E402
from leo.analysis.research.formal_orbit import doppler_hz  # noqa: E402
from leo.sky.frames import geodetic_to_ecef_km  # noqa: E402
from leo.sky.propagation import parse_element_sets  # noqa: E402

FIGURE = ROOT / "reports/figures/2026_09_23_longarc_phase"
ORBIT = ROOT / "reports/artifacts/2026_09_21_shared_identity_orbit"
SIGMA_HZ = 250.0


def fit_candidate_affine(
    observed: np.ndarray,
    predicted: np.ndarray,
    time_s: np.ndarray,
    training: np.ndarray,
) -> dict:
    """Choose a candidate and affine receiver nuisance from training rows only."""
    observed = np.asarray(observed, float)
    predicted = np.asarray(predicted, float)
    time_s = np.asarray(time_s, float)
    training = np.asarray(training, bool)
    if predicted.ndim != 2 or predicted.shape[1] != len(observed):
        raise ValueError("candidate prediction shape mismatch")
    if not (time_s.shape == training.shape == observed.shape) or training.sum() < 3:
        raise ValueError("invalid outer split")
    centre = float(np.mean(time_s[training]))
    design = np.column_stack([np.ones(training.sum()), time_s[training] - centre])
    coefficients, scores = [], []
    for row in predicted:
        coefficient = np.linalg.lstsq(design, observed[training] - row[training], rcond=None)[0]
        residual = observed[training] - row[training] - design @ coefficient
        coefficients.append(coefficient)
        scores.append(float(np.mean((residual / SIGMA_HZ) ** 2)))
    winner = int(np.argmin(scores))
    return {
        "candidate_index": winner,
        "offset_hz": float(coefficients[winner][0]),
        "drift_hz_s": float(coefficients[winner][1]),
        "time_centre_s": centre,
        "training_chi2_per_visit": scores[winner],
        "all_training_chi2_per_visit": scores,
    }


def predict_selected(model: dict, predicted: np.ndarray, time_s: np.ndarray) -> np.ndarray:
    row = predicted[int(model["candidate_index"])]
    return (
        row
        + float(model["offset_hz"])
        + float(model["drift_hz_s"]) * (time_s - float(model["time_centre_s"]))
    )


def equal_visit_rms(residuals: list[np.ndarray]) -> float:
    if not residuals or any(len(row) == 0 for row in residuals):
        raise ValueError("each scored visit needs a response")
    return float(np.sqrt(np.mean([np.mean(np.square(row)) for row in residuals])))


def normalized_frame_cfo(
    frame: dict, observation: dict, fold: str, *, reject_boundary: bool
) -> float | None:
    value = frame["frame"][fold]
    if value is None or (reject_boundary and value["search_boundary"]):
        return None
    scale = observation["historical_rf_normalization_scale"]
    native_period = 1.0 / 4.4e-6
    # The binding froze this integer before phase replay. Never choose a gauge
    # from the held GLRT value or the held odd response.
    lifted_native = (
        value["absolute_cfo_hz"]
        + observation["historical_pilot_alias_index"] * native_period
    )
    expected_period = native_period * scale
    if abs(expected_period - observation["historical_pilot_alias_period_hz"]) > 1e-6:
        raise ValueError("bound RF-normalized alias period changed")
    return float(lifted_native * scale)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    binding_path = FIGURE / "binding.json"
    frames_path = FIGURE / "replay/frames.json.gz"
    cache_path = ORBIT / "candidate-phase-states.npz"
    tle_path = ORBIT / "audit.retained-tles.json.gz"
    fit_path = ORBIT / "fit.json"
    binding = json.loads(binding_path.read_text())
    if digest(cache_path) != binding["candidate_bank_sha256"].removeprefix("sha256:"):
        raise ValueError("candidate bank digest changed")
    with gzip.open(frames_path, "rt") as stream:
        replayed = json.load(stream)
    if replayed["completed_visit_count"] != replayed["expected_visit_count"]:
        raise ValueError("long-arc replay is incomplete")
    fit = json.loads(fit_path.read_text())
    receiver_model = next(
        row for row in fit["models"] if row["identity_model"] == "joint_candidate_mixture"
    )
    receiver = geodetic_to_ecef_km(
        receiver_model["latitude_deg"], receiver_model["longitude_deg"], 0.0
    )
    with np.load(cache_path, allow_pickle=False) as archive:
        index = binding["episode_cache_index"]
        norad = archive[f"norad_{index}"].astype(int)
        if str(archive[f"episode_id_{index}"].item()) != binding["tracklet_id"]:
            raise ValueError("candidate bank episode changed")
        if archive[f"winner_norad_{index}"].item() != binding["cache_winner_norad"]:
            raise ValueError("candidate bank winner changed")
        if str(archive[f"catalogue_digest_{index}"].item()) != binding["cache_catalogue_digest"]:
            raise ValueError("candidate bank catalogue changed")
    if norad.tolist() != binding["cache_candidate_norads"]:
        raise ValueError("candidate shortlist changed")
    with gzip.open(tle_path, "rt") as stream:
        records = json.load(stream)[binding["session_id"]]["records"]
    catalogue = parse_element_sets("".join(records[str(value)] for value in norad))

    rows = sorted(replayed["rows"], key=lambda row: row["observation"]["time_s"])
    times = np.asarray([row["observation"]["time_s"] for row in rows])
    training = np.asarray([row["outer_partition"] == "train" for row in rows])
    reference_ns = binding["historical_inventory"]["reference_utc_ns"]
    p, v, valid = replay.state_arrays(catalogue, list(range(len(norad))), reference_ns, times)
    if not np.array_equal(valid, np.arange(len(norad))):
        raise ValueError("candidate propagation failed")
    predicted = doppler_hz(receiver, p, v)
    glrt = np.asarray([row["observation"]["normalized_cfo_hz"] for row in rows])
    pilot, pilot_times, coverage, held_coherence = [], [], [], []
    held_odd, held_odd_times = [], []
    for row in rows:
        branch = row["branches"][row["selected_seed_index"]]
        observation = row["observation"]
        even = [
            normalized_frame_cfo(frame, observation, "even", reject_boundary=True)
            for frame in branch["frames"]
            if frame["group_id"] in (0, 3, 5) and frame["frame"]["training_supported"]
        ]
        even = [value for value in even if value is not None]
        even_times = [
            frame["session_time_s"]
            for frame in branch["frames"]
            if frame["group_id"] in (0, 3, 5)
            and frame["frame"]["training_supported"]
            and normalized_frame_cfo(frame, observation, "even", reject_boundary=True)
            is not None
        ]
        odd = [
            normalized_frame_cfo(frame, observation, "odd", reject_boundary=False)
            for frame in branch["frames"]
            if frame["group_id"] in (1, 2, 4) and frame["frame"]["training_supported"]
        ]
        odd = [value for value in odd if value is not None]
        odd_times = [
            frame["session_time_s"]
            for frame in branch["frames"]
            if frame["group_id"] in (1, 2, 4)
            and frame["frame"]["training_supported"]
            and normalized_frame_cfo(frame, observation, "odd", reject_boundary=False)
            is not None
        ]
        odd_frames = [
            frame["frame"]["odd"]
            for frame in branch["frames"]
            if frame["group_id"] in (1, 2, 4)
            and frame["frame"]["training_supported"]
            and frame["frame"]["odd"] is not None
        ]
        pilot.append(float(np.mean(even)) if even else np.nan)
        pilot_times.append(float(np.mean(even_times)) if even_times else np.nan)
        held_odd.append(np.asarray(odd))
        held_odd_times.append(np.asarray(odd_times))
        held_coherence.append(
            {
                "exact": float(np.mean([item["exact_coherence"] for item in odd_frames])),
                "control": float(np.mean([item["control_coherence"] for item in odd_frames])),
                "search_boundary_count": sum(item["search_boundary"] for item in odd_frames),
            }
        )
        coverage.append(
            {"visit_index": observation["visit_index"], "even": len(even), "odd": len(odd)}
        )
    pilot = np.asarray(pilot)
    pilot_times = np.asarray(pilot_times)
    fit_mask = training & np.isfinite(pilot)
    glrt_model = fit_candidate_affine(glrt, predicted, times, training)
    pp, pv, pvalid = replay.state_arrays(
        catalogue, list(range(len(norad))), reference_ns, pilot_times
    )
    if not np.array_equal(pvalid, np.arange(len(norad))):
        raise ValueError("pilot-time candidate propagation failed")
    pilot_predicted = doppler_hz(receiver, pp, pv)
    pilot_model = fit_candidate_affine(pilot, pilot_predicted, pilot_times, fit_mask)
    held_indices = np.flatnonzero(~training)
    common = [index for index in held_indices if len(held_odd[index])]
    held_prediction = {"archived_glrt": [], "training_even_pilot": []}
    for index in common:
        hp, hv, hvalid = replay.state_arrays(
            catalogue, list(range(len(norad))), reference_ns, held_odd_times[index]
        )
        if not np.array_equal(hvalid, np.arange(len(norad))):
            raise ValueError("held-frame candidate propagation failed")
        candidate = doppler_hz(receiver, hp, hv)
        held_prediction["archived_glrt"].append(
            predict_selected(glrt_model, candidate, held_odd_times[index])
        )
        held_prediction["training_even_pilot"].append(
            predict_selected(pilot_model, candidate, held_odd_times[index])
        )
    residuals = {
        name: [
            held_odd[index] - prediction
            for index, prediction in zip(common, predictions, strict=True)
        ]
        for name, predictions in held_prediction.items()
    }
    visit_rms = {
        name: np.asarray([np.sqrt(np.mean(np.square(row))) for row in values])
        for name, values in residuals.items()
    }
    output = {
        "schema": "longarc-phase-evaluation/v1",
        "scope": "source-seeded conditional CFO comparison; no decoded identity or position claim",
        "receiver_reference": {
            "kind": "frozen RF-derived joint-candidate fit; not receiver truth",
            "latitude_deg": receiver_model["latitude_deg"],
            "longitude_deg": receiver_model["longitude_deg"],
        },
        "sigma_hz": SIGMA_HZ,
        "response_gauge": (
            "binding-frozen native pilot alias index applied before RF normalization; "
            "held GLRT and held odd values never choose the alias"
        ),
        "conditional_calibration": (
            "each visit's branch and support mask use even frames in groups 0,3,5; "
            "outer candidate and affine nuisance use outer-train visits only; held odd "
            "groups 1,2,4 are a shared response"
        ),
        "candidate_norad": norad.tolist(),
        "outer_train_visits": int(training.sum()),
        "outer_held_visits": int((~training).sum()),
        "common_held_visits": len(common),
        "glrt_model": {**glrt_model, "norad": int(norad[glrt_model["candidate_index"]])},
        "pilot_model": {**pilot_model, "norad": int(norad[pilot_model["candidate_index"]])},
        "held_odd_equal_visit_rms_hz": {
            "archived_glrt": equal_visit_rms(
                residuals["archived_glrt"]
            ),
            "training_even_pilot": equal_visit_rms(
                residuals["training_even_pilot"]
            ),
        },
        "held_odd_visit_rms_hz_quantiles_0_25_50_75_100": {
            name: np.quantile(values, [0, 0.25, 0.5, 0.75, 1]).tolist()
            for name, values in visit_rms.items()
        },
        "held_odd_visit_win_counts": {
            "archived_glrt": int(
                np.sum(visit_rms["archived_glrt"] < visit_rms["training_even_pilot"])
            ),
            "training_even_pilot": int(
                np.sum(visit_rms["training_even_pilot"] < visit_rms["archived_glrt"])
            ),
            "ties": int(
                np.sum(visit_rms["training_even_pilot"] == visit_rms["archived_glrt"])
            ),
        },
        "held_odd_visits": [
            {
                "visit_index": rows[index]["observation"]["visit_index"],
                "time_s": float(times[index]),
                "response_count": len(held_odd[index]),
                "archived_glrt_mean_residual_hz": float(
                    np.mean(residuals["archived_glrt"][position])
                ),
                "archived_glrt_rms_hz": float(
                    visit_rms["archived_glrt"][position]
                ),
                "training_even_pilot_mean_residual_hz": float(
                    np.mean(residuals["training_even_pilot"][position])
                ),
                "training_even_pilot_rms_hz": float(
                    visit_rms["training_even_pilot"][position]
                ),
            }
            for position, index in enumerate(common)
        ],
        "held_odd_equal_visit_coherence": {
            "exact": float(np.mean([held_coherence[index]["exact"] for index in held_indices])),
            "control": float(
                np.mean([held_coherence[index]["control"] for index in held_indices])
            ),
            "search_boundary_frames_retained": int(
                sum(held_coherence[index]["search_boundary_count"] for index in held_indices)
            ),
        },
        "coverage": coverage,
        "held_odd_used_for_selection_or_gating": False,
        "input_sha256": {
            str(path.relative_to(ROOT)): digest(path)
            for path in (binding_path, frames_path, cache_path, tle_path, fit_path)
        },
        "source_sha256": digest(Path(__file__)),
        "formal_orbit_source_sha256": digest(Path(formal_orbit_module.__file__)),
    }
    target = FIGURE / "evaluation.json"
    target.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
