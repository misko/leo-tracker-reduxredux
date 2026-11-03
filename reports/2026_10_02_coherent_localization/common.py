import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "2026_10_02_full_curve_glrt"
TRACK_SOURCE = ROOT.parent / "2026_10_02_shared_rx_position"
ALIAS_HZ = 1 / 4.4e-6


def circular(measured, prediction=0):
    return (measured - prediction + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def coordinates(point):
    east, north = point
    angular = np.hypot(east, north) / 6371.0088
    bearing = np.arctan2(east, north)
    latitude, longitude = np.deg2rad([38.5816, -121.4944])
    result_lat = np.arcsin(
        np.sin(latitude) * np.cos(angular) + np.cos(latitude) * np.sin(angular) * np.cos(bearing)
    )
    result_lon = longitude + np.arctan2(
        np.sin(bearing) * np.sin(angular) * np.cos(latitude),
        np.cos(angular) - np.sin(latitude) * np.sin(result_lat),
    )
    return np.rad2deg([result_lat, result_lon])


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


def rho(errors):
    return 2 * 200**2 * (np.sqrt(1 + (np.minimum(np.abs(errors), 2000) / 200) ** 2) - 1)


class Data:
    def __init__(self):
        with np.load(SOURCE / "inputs.npz") as arrays:
            for name in ("times", "measured", "rf", "receiver", "channel", "group", "margin"):
                setattr(self, name, arrays[name])
        with np.load(SOURCE / "satellite-time-states-10s.npz") as states:
            self.nodes = states["nodes"]
            self.position = states["position"]
            self.velocity = states["velocity"]
            self.numbers = states["numbers"]
        metadata = json.loads((SOURCE / "inputs.json").read_text())
        self.session_id = metadata["session_id"]
        solution = metadata["solution"]
        self.initial = np.zeros(6 + len(self.numbers))
        self.initial[:2] = [solution["east_km"], solution["north_km"]]
        for receiver in (0, 1):
            correction = solution["parameters"][str(receiver)]
            self.initial[2 + receiver * 2 : 4 + receiver * 2] = [
                correction["intercept_hz_at_150s"],
                correction["slope_hz_s"],
            ]
        index = defaultdict(list)
        for row in range(len(self.times)):
            index[(round(float(self.times[row]), 8), self.receiver[row], self.rf[row])].append(row)
        with np.load(TRACK_SOURCE / "inputs.npz") as archive:
            source = {key: archive[key] for key in ("times", "receiver", "rf", "measured", "track")}
        joined = []
        maximum_error = 0.0
        for row in range(len(source["times"])):
            key = (
                round(float(source["times"][row]), 8),
                source["receiver"][row],
                source["rf"][row],
            )
            alternatives = np.array(index[key], dtype=int)
            error = np.abs(circular(self.measured[alternatives], source["measured"][row]))
            equivalent = alternatives[error < 0.01]
            if not len(equivalent) or len(np.unique(self.group[equivalent])) != 1:
                raise ValueError(
                    "Track observation cannot be unambiguously joined to a source group"
                )
            chosen = int(equivalent[0])
            joined.append(chosen)
            maximum_error = max(
                maximum_error, abs(float(circular(self.measured[chosen], source["measured"][row])))
            )
        joined = np.array(joined, dtype=int)
        self.tracks = [
            {
                "track_id": track["track_id"],
                "rows": joined[source["track"] == track_index],
                "candidate_indices": np.arange(len(self.numbers)),
                "receiver": track["receiver"],
                "channel": track["channel"],
            }
            for track_index, track in enumerate(metadata["source"]["tracks"])
        ]
        self.join_receipt = {
            "track_observations": len(joined),
            "unique_source_groups": len(np.unique(self.group[joined])),
            "maximum_circular_join_error_hz": maximum_error,
            "policy": (
                "exact time rounded to 10ns, RX, RF; circular error <0.01Hz; single source group"
            ),
        }

    def predict(self, parameters, rows=None, satellites=None):
        if (rows is None) != (satellites is None):
            raise ValueError("Supply paired rows and satellites, or neither")
        if rows is None:
            rows = np.arange(len(self.times))[:, None]
            satellites = np.arange(len(self.numbers))[None, :]
        else:
            rows = np.asarray(rows, dtype=int)
            satellites = np.asarray(satellites, dtype=int)
            if rows.shape != satellites.shape:
                raise ValueError("Paired rows and satellite indices must have identical shapes")
        query = self.times[rows] + parameters[6:][satellites]
        if np.any(query < self.nodes[0]) or np.any(query >= self.nodes[-1]):
            raise ValueError("Shifted orbit time lies outside the exported ephemeris")
        fraction = (query - self.nodes[0]) / (self.nodes[1] - self.nodes[0])
        lower = np.floor(fraction).astype(int)
        weight = (fraction - lower)[..., None]
        position = (
            self.position[satellites, lower] * (1 - weight)
            + self.position[satellites, lower + 1] * weight
        )
        velocity = (
            self.velocity[satellites, lower] * (1 - weight)
            + self.velocity[satellites, lower + 1] * weight
        )
        latitude, longitude = coordinates(parameters[:2])
        delta = position - ecef(latitude, longitude)
        direction = delta / np.linalg.norm(delta, axis=-1)[..., None]
        latitude_rad, longitude_rad = np.deg2rad([latitude, longitude])
        up = np.array(
            [
                np.cos(latitude_rad) * np.cos(longitude_rad),
                np.cos(latitude_rad) * np.sin(longitude_rad),
                np.sin(latitude_rad),
            ]
        )
        offset = parameters[2 + 2 * self.receiver[rows]] + parameters[
            3 + 2 * self.receiver[rows]
        ] * (self.times[rows] - 150)
        prediction = -self.rf[rows] * np.sum(direction * velocity, axis=-1) / 299792.458 + offset
        return prediction, np.sum(direction * up, axis=-1) >= 0


def jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value
