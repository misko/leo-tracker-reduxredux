import json
import time
from pathlib import Path

import numpy as np
from model import ALIAS_HZ, UNMATCHED_COST, fit_independent, fit_shared, loss
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent
LATITUDE = 38.5816
LONGITUDE = -121.4944


def coordinates(east, north):
    angular = np.hypot(east, north) / 6371.0088
    bearing = np.arctan2(east, north)
    latitude, longitude = np.deg2rad([LATITUDE, LONGITUDE])
    result_lat = np.arcsin(
        np.sin(latitude) * np.cos(angular) + np.cos(latitude) * np.sin(angular) * np.cos(bearing)
    )
    result_lon = longitude + np.arctan2(
        np.sin(bearing) * np.sin(angular) * np.cos(latitude),
        np.cos(angular) - np.sin(latitude) * np.sin(result_lat),
    )
    return np.rad2deg([result_lat, result_lon])


def receiver_ecef(latitude, longitude):
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
    def __init__(self):
        source = np.load(ROOT / "inputs.npz")
        self.metadata = json.loads((ROOT / "inputs.json").read_text())
        self.groups = [
            np.flatnonzero(source["track"] == index)
            for index in range(len(self.metadata["tracks"]))
        ]
        width = max(map(len, self.groups))
        indices = np.zeros((len(self.groups), width), dtype=int)
        self.valid = np.zeros(indices.shape, dtype=bool)
        for index, group in enumerate(self.groups):
            indices[index, : len(group)] = group
            self.valid[index, : len(group)] = True
        self.times = source["times"][indices] - 150
        self.measured = source["measured"][indices]
        self.rf = source["rf"][indices]
        self.position = source["position"][indices].transpose(0, 2, 1, 3)
        self.velocity = source["velocity"][indices].transpose(0, 2, 1, 3)
        self.receivers = source["receiver"][indices[:, 0]]
        starts = np.min(np.where(self.valid, self.times, np.inf), axis=1)
        stops = np.max(np.where(self.valid, self.times, -np.inf), axis=1)
        self.training = self.valid & (self.times < (starts + (stops - starts) * 2 / 3)[:, None])
        self.evaluation = self.valid & ~self.training
        assert np.all(self.training.sum(axis=1) > 0)
        assert np.all(self.evaluation.sum(axis=1) > 0)

    def evaluate(self, point, mode, details=False):
        latitude, longitude = coordinates(*point)
        receiver = receiver_ecef(latitude, longitude)
        delta = self.position - receiver
        direction = delta / np.linalg.norm(delta, axis=-1)[..., None]
        prediction = -self.rf[:, None, :] * np.sum(direction * self.velocity, axis=-1) / 299792.458
        residual = self.measured[:, None, :] - prediction
        lat_rad, lon_rad = np.deg2rad([latitude, longitude])
        up = np.array(
            [np.cos(lat_rad) * np.cos(lon_rad), np.cos(lat_rad) * np.sin(lon_rad), np.sin(lat_rad)]
        )
        visible = np.any((np.sum(direction * up, axis=-1) >= 0) & self.training[:, None, :], axis=2)
        correction = np.zeros(self.times.shape)
        selected = np.zeros(len(self.groups), dtype=int)
        branches = np.zeros(len(self.groups))
        costs = np.zeros(len(self.groups))
        parameters = {}
        if mode == "independent":
            fit = fit_independent(residual, self.training, visible)
            selected, costs = fit["selected"], fit["costs"]
            correction[:] = fit["offsets"][:, None]
        else:
            for receiver_id in (0, 1):
                rows = self.receivers == receiver_id
                fit = fit_shared(
                    residual[rows],
                    self.times[rows],
                    self.training[rows],
                    visible[rows],
                    10 if mode == "linear" else 0,
                )
                selected[rows], costs[rows] = fit["selected"], fit["costs"]
                branches[rows] = fit["branches"]
                correction[rows] = (
                    fit["intercept"]
                    + fit["slope"] * self.times[rows]
                    + fit["branches"][:, None] * ALIAS_HZ
                )
                parameters[str(receiver_id)] = {
                    "intercept_hz_at_150s": fit["intercept"],
                    "slope_hz_s": fit["slope"],
                }
        score = float(np.mean(np.minimum(costs, UNMATCHED_COST)))
        if not details:
            return score
        errors = residual[np.arange(len(selected)), selected] - correction
        accepted = costs < UNMATCHED_COST
        eval_cost = (loss(errors) * self.evaluation).sum(axis=1) / self.evaluation.sum(axis=1)
        evaluation_score = float(
            np.mean(np.where(accepted, np.minimum(eval_cost, UNMATCHED_COST), UNMATCHED_COST))
        )
        track_rows = []
        for index, metadata in enumerate(self.metadata["tracks"]):
            track_rows.append(
                {
                    "track_id": metadata["track_id"],
                    "receiver": int(self.receivers[index]),
                    "channel": metadata["channel"],
                    "catalog_number": metadata["catalog_numbers"][selected[index]],
                    "accepted": bool(accepted[index]),
                    "alias_branch": int(branches[index]),
                    "training_offset_hz": float(
                        np.mean(residual[index, selected[index], self.training[index]])
                        - branches[index] * ALIAS_HZ
                    ),
                    "training_mean_time_s": float(
                        np.mean(self.times[index, self.training[index]]) + 150
                    ),
                    "midpoint_s": float(
                        (
                            self.times[index, self.valid[index]].min()
                            + self.times[index, self.valid[index]].max()
                        )
                        / 2
                        + 150
                    ),
                    "training_rms_hz": float(
                        np.sqrt(np.mean(errors[index, self.training[index]] ** 2))
                    ),
                    "evaluation_rms_hz": float(
                        np.sqrt(np.mean(errors[index, self.evaluation[index]] ** 2))
                    ),
                }
            )
        return {
            "east_km": float(point[0]),
            "north_km": float(point[1]),
            "latitude": float(latitude),
            "longitude": float(longitude),
            "training_cost": score,
            "evaluation_cost": evaluation_score,
            "accepted_tracks": int(accepted.sum()),
            "parameters": parameters,
            "tracks": track_rows,
        }


def main():
    started = time.monotonic()
    experiment = Experiment()
    results = {
        "protocol": (
            "conditional fixed-site top-five shortlist; zero time shift; altitude 0m; "
            "equal track weights; soft-L1 200Hz; unmatched cap equivalent to 2000Hz; "
            "train on first 2/3 of each track time span; no test-based selection"
        ),
        "models": {},
    }
    for mode in ("independent", "constant", "linear"):
        grid = []
        for east in np.arange(-200, 201, 50):
            for north in np.arange(-200, 201, 50):
                point = [float(east), float(north)]
                grid.append({"point": point, "cost": experiment.evaluate(point, mode)})
        seeds = sorted(grid, key=lambda row: row["cost"])[:2]
        candidates = [(row["cost"], row["point"]) for row in seeds]
        refinements = []
        for seed in seeds:
            fitted = minimize(
                lambda point, model=mode: experiment.evaluate(point, model),
                seed["point"],
                method="Powell",
                bounds=[(-200, 200), (-200, 200)],
                options={"maxfev": 160, "xtol": 0.05, "ftol": 1e-5},
            )
            candidates.append((float(fitted.fun), fitted.x.tolist()))
            refinements.append(
                {
                    "success": bool(fitted.success),
                    "evaluations": int(fitted.nfev),
                    "message": str(fitted.message),
                }
            )
        point = min(candidates, key=lambda row: row[0])[1]
        result = experiment.evaluate(point, mode, details=True)
        reference = experiment.metadata["reference_site"]
        result["reference_error_km"] = float(
            np.linalg.norm(
                receiver_ecef(result["latitude"], result["longitude"])
                - receiver_ecef(reference["latitude_deg"], reference["longitude_deg"])
            )
        )
        result["grid"], result["refinements"] = grid, refinements
        results["models"][mode] = result
        results["elapsed_s"] = time.monotonic() - started
        (ROOT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        print(
            json.dumps(
                {key: value for key, value in result.items() if key not in ("tracks", "grid")}
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
