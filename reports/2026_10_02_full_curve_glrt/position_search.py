import argparse
import json
import time
from pathlib import Path

import numpy as np
from matching import circular_residual
from position_loss import CAP_HZ, SCALE_HZ, best_group_rows, profile_receiver, rho, training_mask
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent
PRIOR_LATITUDE = 38.5816
PRIOR_LONGITUDE = -121.4944


def coordinates(east, north):
    angular = np.hypot(east, north) / 6371.0088
    bearing = np.arctan2(east, north)
    latitude, longitude = np.deg2rad([PRIOR_LATITUDE, PRIOR_LONGITUDE])
    result_latitude = np.arcsin(
        np.sin(latitude) * np.cos(angular) + np.cos(latitude) * np.sin(angular) * np.cos(bearing)
    )
    result_longitude = longitude + np.arctan2(
        np.sin(bearing) * np.sin(angular) * np.cos(latitude),
        np.cos(angular) - np.sin(latitude) * np.sin(result_latitude),
    )
    return np.rad2deg([result_latitude, result_longitude])


def ecef(latitude, longitude):
    latitude, longitude = np.deg2rad([latitude, longitude])
    eccentricity = (1 / 298.257223563) * (2 - 1 / 298.257223563)
    radius = 6378.137 / np.sqrt(1 - eccentricity * np.sin(latitude) ** 2)
    return np.array(
        [
            radius * np.cos(latitude) * np.cos(longitude),
            radius * np.cos(latitude) * np.sin(longitude),
            radius * (1 - eccentricity) * np.sin(latitude),
        ]
    )


class Experiment:
    def __init__(self, all_training=False, states_path=None, candidate_limit=None):
        self.data = np.load(ROOT / "inputs.npz")
        self.metadata = json.loads((ROOT / "inputs.json").read_text())
        states = np.load(states_path or ROOT / "position-states.npz")
        if states_path is None:
            np.testing.assert_array_equal(states["numbers"], self.data["selected_numbers"])
        limit = len(states["numbers"]) if candidate_limit is None else candidate_limit
        if not 1 <= limit <= len(states["numbers"]):
            raise ValueError("candidate limit outside available state bank")
        self.candidate_numbers = states["numbers"][:limit]
        assert len(np.unique(self.candidate_numbers)) == limit
        self.position = states["position"][:, :limit]
        self.velocity = states["velocity"][:, :limit]
        self.times = self.data["times"] - 150
        self.groups = self.data["group"]
        counts = np.bincount(self.groups)
        group_times = np.bincount(self.groups, weights=self.times + 150) / counts
        self.group_training = training_mask(group_times, all_training)
        self.training = self.group_training[self.groups]
        self.initial = np.array(
            [
                [
                    self.metadata["solution"]["parameters"][str(receiver)]["intercept_hz_at_150s"],
                    self.metadata["solution"]["parameters"][str(receiver)]["slope_hz_s"],
                ]
                for receiver in (0, 1)
            ]
        )
        self.evaluations = 0

    def evaluate(self, point, profile, details=False, phase_shift_hz=0):
        self.evaluations += 1
        latitude, longitude = coordinates(*point)
        receiver = ecef(latitude, longitude)
        delta = self.position - receiver
        direction = delta / np.linalg.norm(delta, axis=-1)[..., None]
        prediction = (
            -self.data["rf"][:, None] * np.sum(direction * self.velocity, axis=-1) / 299792.458
        )
        latitude_rad, longitude_rad = np.deg2rad([latitude, longitude])
        up = np.array(
            [
                np.cos(latitude_rad) * np.cos(longitude_rad),
                np.cos(latitude_rad) * np.sin(longitude_rad),
                np.sin(latitude_rad),
            ]
        )
        visible = np.sum(direction * up, axis=-1) >= 0
        base = self.data["measured"][:, None] - prediction - phase_shift_hz
        parameters = self.initial.copy()
        if profile:
            for receiver_id in (0, 1):
                lane = self.data["receiver"] == receiver_id
                local = base[lane].copy()
                local[~visible[lane]] = np.nan
                parameters[receiver_id] = profile_receiver(
                    local,
                    self.groups[lane],
                    self.times[lane],
                    self.training[lane],
                    parameters[receiver_id],
                )
        correction = (
            parameters[self.data["receiver"], 0] + parameters[self.data["receiver"], 1] * self.times
        )
        residual = circular_residual(base, correction[:, None])
        residual[~visible] = np.inf
        rows, satellites, errors = best_group_rows(residual, self.groups)
        group_train = self.training[rows]
        score = float(np.mean(rho(errors[group_train])))
        if not details:
            return score
        evaluation = ~group_train
        fit_mask = np.isfinite(errors) & (np.abs(errors) < 1000)
        return {
            "point": list(map(float, point)),
            "latitude": float(latitude),
            "longitude": float(longitude),
            "training_loss": score,
            "evaluation_loss": (
                float(np.mean(rho(errors[evaluation]))) if np.any(evaluation) else None
            ),
            "training_groups": int(group_train.sum()),
            "evaluation_groups": int(evaluation.sum()),
            "training_within_1000hz": int(np.sum(fit_mask & group_train)),
            "evaluation_within_1000hz": int(np.sum(fit_mask & evaluation)),
            "parameters": parameters.tolist(),
            "within_gate_evaluation_rms_hz": (
                float(np.sqrt(np.mean(errors[evaluation & fit_mask] ** 2)))
                if np.any(evaluation & fit_mask)
                else None
            ),
            "within_gate_training_rms_hz": (
                float(np.sqrt(np.mean(errors[group_train & fit_mask] ** 2)))
                if np.any(group_train & fit_mask)
                else None
            ),
        }


def main(all_training=False):
    started = time.monotonic()
    experiment = Experiment(all_training=all_training)
    destination = ROOT / (
        "position-results-all-training.json" if all_training else "position-results.json"
    )
    previous = experiment.metadata["solution"]
    original = [previous["east_km"], previous["north_km"]]
    results = {
        "protocol": {
            "loss": (
                "mean over fixed source groups of capped soft-L1 nearest visible "
                "selected-satellite / GLRT candidate circular residual"
            ),
            "scale_hz": SCALE_HZ,
            "cap_hz": CAP_HZ,
            "satellite_count": len(experiment.data["selected_numbers"]),
            "scope": (
                "all gate-passing projections; no per-position dropping or continuity selection; "
                "equal source-group weights"
            ),
            "partition": (
                "all source groups used for fitting; no holdout"
                if all_training
                else "fixed 10s blocks: two training, one evaluation; "
                "no evaluation-based model selection"
            ),
            "qualification": (
                "conditional known-site shortlist and previously fit nuisance initialization; "
                "not independent validation"
            ),
            "altitude_m": 0,
            "region": "Sacramento-centered east/north +/-200km",
            "slope_bound_hz_s": 10,
        },
        "models": {"original": experiment.evaluate(original, False, details=True)},
    }
    for name, profile in (("fixed_rx", False), ("profiled_rx", True)):
        grid = []
        for east in np.arange(-200, 201, 50):
            for north in np.arange(-200, 201, 50):
                point = [float(east), float(north)]
                grid.append({"point": point, "loss": experiment.evaluate(point, profile)})
        seeds = [original, *[row["point"] for row in sorted(grid, key=lambda row: row["loss"])[:2]]]
        candidates = [(experiment.evaluate(point, profile), point) for point in seeds]
        refinements = []
        for seed in seeds:
            simplex = np.tile(seed, (3, 1))
            simplex[1, 0] += 2 if seed[0] < 198 else -2
            simplex[2, 1] += 2 if seed[1] < 198 else -2
            fit = minimize(
                lambda point, mode=profile: experiment.evaluate(point, mode),
                seed,
                method="Nelder-Mead",
                bounds=[(-200, 200), (-200, 200)],
                options={
                    "maxfev": 180,
                    "xatol": 0.03,
                    "fatol": 1.0,
                    "initial_simplex": simplex,
                },
            )
            candidates.append((float(fit.fun), fit.x.tolist()))
            refinements.append(
                {
                    "point": fit.x.tolist(),
                    "loss": float(fit.fun),
                    "success": bool(fit.success),
                    "evaluations": int(fit.nfev),
                }
            )
        winner = min(candidates, key=lambda row: row[0])[1]
        result = experiment.evaluate(winner, profile, details=True)
        result["grid"], result["refinements"] = grid, refinements
        results["models"][name] = result
        results["elapsed_s"] = time.monotonic() - started
        destination.write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")
        print(
            json.dumps(
                {key: value for key, value in result.items() if key not in ("grid", "refinements")}
            ),
            flush=True,
        )
    reference = experiment.metadata["source"]["reference_site"]
    for result in results["models"].values():
        result["reference_error_km"] = float(
            np.linalg.norm(
                ecef(result["latitude"], result["longitude"])
                - ecef(reference["latitude_deg"], reference["longitude_deg"])
            )
        )
    results["elapsed_s"] = time.monotonic() - started
    results["objective_evaluations"] = experiment.evaluations
    destination.write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-training", action="store_true")
    main(all_training=parser.parse_args().all_training)
