"""Truth-free numerical ports for Sacramento T1AT/C0 and V16 positioning.

The observation inventory is fixed before geographic search. Reference positions
belong to evaluation products, never to these inference inputs.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass(frozen=True)
class PositionScore:
    name: Literal["T1AT", "V16"]
    sigma_hz: float
    detection_budget: float
    clutter_rate: float
    common_sigma_s: float
    relative_sigma_s: float

    def __post_init__(self):
        values = (
            self.sigma_hz,
            self.detection_budget,
            self.clutter_rate,
            self.common_sigma_s,
            self.relative_sigma_s,
        )
        if self.name not in ("T1AT", "V16") or any(not np.isfinite(v) or v <= 0 for v in values):
            raise ValueError("invalid position score")


POSITION_SCORES = {
    "T1AT": PositionScore("T1AT", 200.0, 0.8, 2.0, 10.0, 1.0),
    "V16": PositionScore("V16", 125.0, 1.6, 0.5, 3.0, 0.15),
}


@dataclass(frozen=True)
class RegionalPrior:
    latitude_deg: float = 38.5816
    longitude_deg: float = -121.4944
    radius_km: float = 250.0
    altitude_m: float = 0.0

    def __post_init__(self):
        if (
            not np.isfinite(
                (self.latitude_deg, self.longitude_deg, self.radius_km, self.altitude_m)
            ).all()
            or not -90 <= self.latitude_deg <= 90
            or not -180 <= self.longitude_deg <= 180
            or not 0 < self.radius_km <= 500
        ):
            raise ValueError("invalid regional prior")


def _array(value, dtype):
    result = np.array(value, dtype=dtype, copy=True)
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class PositionObservations:
    window_ids: tuple[str, ...]
    times_s: np.ndarray
    measured_hz: np.ndarray
    rf_hz: np.ndarray
    receiver: np.ndarray
    channel: np.ndarray
    margin: np.ndarray

    def __post_init__(self):
        n = len(self.window_ids)
        if n == 0 or len(set(self.window_ids)) != n or any(not x for x in self.window_ids):
            raise ValueError("one observation per unique nonempty window is required")
        for name in ("times_s", "measured_hz", "rf_hz", "receiver", "channel", "margin"):
            value = np.asarray(getattr(self, name))
            if value.shape != (n,) or not np.isfinite(value).all():
                raise ValueError(f"invalid observation {name}")
            integral = name in ("receiver", "channel")
            if integral and (np.any(value != np.floor(value)) or np.any(value < 0)):
                raise ValueError(f"invalid observation {name}")
            object.__setattr__(self, name, _array(value, int if integral else float))
        if np.any(self.rf_hz <= 0) or not set(self.receiver) <= {0, 1}:
            raise ValueError("positive RF and receiver 0/1 required")

    @property
    def time_center_s(self) -> float:
        return float((self.times_s.min() + self.times_s.max()) / 2)

    @property
    def rf_center_hz(self) -> float:
        return float(np.mean(np.unique(self.rf_hz)))


@dataclass(frozen=True)
class PositionOrbitBank:
    numbers: np.ndarray
    nodes_s: np.ndarray
    position_km: np.ndarray
    velocity_km_s: np.ndarray

    def __post_init__(self):
        numbers, nodes = np.asarray(self.numbers), np.asarray(self.nodes_s)
        if (
            numbers.ndim != 1
            or len(numbers) < 1
            or np.any(numbers <= 0)
            or not np.isfinite(numbers).all()
            or np.any(numbers != np.floor(numbers))
            or len(np.unique(numbers)) != len(numbers)
        ):
            raise ValueError("unique positive catalogue numbers required")
        if (
            nodes.ndim != 1
            or len(nodes) < 2
            or not np.isfinite(nodes).all()
            or np.any(np.diff(nodes) <= 0)
            or not np.allclose(np.diff(nodes), nodes[1] - nodes[0], rtol=0, atol=1e-9)
        ):
            raise ValueError("regular increasing ephemeris nodes required")
        shape = (len(numbers), len(nodes), 3)
        for name in ("position_km", "velocity_km_s"):
            value = np.asarray(getattr(self, name))
            if value.shape != shape or not np.isfinite(value).all():
                raise ValueError(f"invalid orbit {name}")
            object.__setattr__(self, name, _array(value, float))
        object.__setattr__(self, "numbers", _array(numbers, int))
        object.__setattr__(self, "nodes_s", _array(nodes, float))

    def select(self, indices):
        return PositionOrbitBank(
            self.numbers[indices],
            self.nodes_s,
            self.position_km[indices],
            self.velocity_km_s[indices],
        )
