"""Prediction-only transport of a trained receiver/group correction function."""

from dataclasses import dataclass

import numpy as np

from leo.analysis.channel_group_calibration import GroupCalibrationFrame


def readonly(value):
    array = np.array(value, float, copy=True)
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class FrozenGroupCalibration:
    time_center_s: float
    rf_center_hz: float
    frame: GroupCalibrationFrame
    receiver_rf_coefficients: np.ndarray
    baseline_affine: np.ndarray
    group_offsets_hz: np.ndarray
    group_drifts_hz_s: np.ndarray
    clock_nodes_s: np.ndarray
    clock_knots_hz: np.ndarray
    group_clock_knots_hz: np.ndarray | None = None

    def __post_init__(self):
        if not np.isfinite([self.time_center_s, self.rf_center_hz]).all() or self.rf_center_hz <= 0:
            raise ValueError("finite trained time/RF centering required")
        for name in (
            "receiver_rf_coefficients",
            "baseline_affine",
            "group_offsets_hz",
            "group_drifts_hz_s",
            "clock_nodes_s",
            "clock_knots_hz",
        ):
            value = readonly(getattr(self, name))
            if not np.isfinite(value).all():
                raise ValueError("finite frozen calibration coefficients required")
            object.__setattr__(self, name, value)
        count = len(self.frame.receivers)
        group_knots = (
            np.zeros((count, len(self.clock_nodes_s)))
            if self.group_clock_knots_hz is None
            else readonly(self.group_clock_knots_hz)
        )
        if (
            group_knots.shape != (count, len(self.clock_nodes_s))
            or not np.isfinite(group_knots).all()
        ):
            raise ValueError("frozen differential clock dimensions differ")
        object.__setattr__(self, "group_clock_knots_hz", readonly(group_knots))
        if (
            self.receiver_rf_coefficients.shape != (5,)
            or self.baseline_affine.shape != (2, 2)
            or self.group_offsets_hz.shape != (count,)
            or self.group_drifts_hz_s.shape not in ((0,), (count,))
            or self.clock_nodes_s.ndim != 1
            or self.clock_knots_hz.shape != (2, len(self.clock_nodes_s))
        ):
            raise ValueError("frozen receiver/group calibration dimensions differ")
        if len(self.clock_nodes_s) and np.any(np.diff(self.clock_nodes_s) <= 0):
            raise ValueError("strictly increasing frozen clock nodes required")

    def predict(self, times_s, rf_hz, receiver, high_group):
        times, rf, rx = np.asarray(times_s), np.asarray(rf_hz), np.asarray(receiver)
        if (
            times.ndim != 1
            or rf.shape != times.shape
            or rx.shape != times.shape
            or not np.isfinite(times).all()
            or not np.isfinite(rf).all()
            or np.any(rf <= 0)
        ):
            raise ValueError("aligned finite native time/RF prediction rows required")
        groups = self.frame.design(rx, high_group)
        rx = rx.astype(int)
        dt = times - self.time_center_s
        v = self.receiver_rf_coefficients
        correction = (
            self.baseline_affine[rx, 0]
            + self.baseline_affine[rx, 1] * dt
            + v[2 * rx]
            + v[2 * rx + 1] * dt
            + v[4] * (rf - self.rf_center_hz) / 1e9
            + groups @ self.group_offsets_hz
        )
        if len(self.group_drifts_hz_s):
            correction += (groups @ self.group_drifts_hz_s) * dt
        if len(self.clock_nodes_s):
            if np.any(times < self.clock_nodes_s[0]) or np.any(times > self.clock_nodes_s[-1]):
                raise ValueError("held times outside declared clock-function support")
            correction += np.array(
                [
                    np.interp(t, self.clock_nodes_s, self.clock_knots_hz[r])
                    for t, r in zip(times, rx, strict=True)
                ]
            )
            correction += (
                np.sum(
                    groups
                    * np.column_stack(
                        [
                            np.interp(times, self.clock_nodes_s, knots)
                            for knots in self.group_clock_knots_hz
                        ]
                    ),
                    axis=1,
                )
                if groups.shape[1]
                else 0
            )
        return correction


def freeze_group_calibration(model, fit):
    """Extract functional terms and prove closure before any held-data prediction."""
    observations = model.observations
    dt = observations.times_s - observations.time_center_s
    affine = np.zeros((2, 2))
    for rx in (0, 1):
        mask = observations.receiver == rx
        if not mask.any():
            continue
        x = np.column_stack([np.ones(mask.sum()), dt[mask]])
        values = model.base.baseline[mask]
        affine[rx] = np.linalg.lstsq(x, values, rcond=None)[0]
        if np.max(abs(x @ affine[rx] - values)) > 1e-6:
            raise ValueError("a non-affine baseline needs its own explicit frozen function")
    clock, group = model.split(fit["nuisance"])
    if model.clock_count:
        if len(clock) != 2 * model.base.null.shape[1]:
            raise ValueError("extra RF-time/satellite corrections need explicit separate transport")
        nodes = model.base.nodes
        knots = clock.reshape(2, -1) @ model.base.null.T
    else:
        nodes, knots = np.empty(0), np.empty((2, 0))
    state = FrozenGroupCalibration(
        observations.time_center_s,
        observations.rf_center_hz,
        model.frame,
        np.asarray(fit["vector"])[2:7],
        affine,
        group[: model.offset_count],
        group[model.offset_count : model.offset_count + model.drift_count],
        nodes,
        knots,
        (
            group[model.offset_count + model.drift_count :].reshape(model.offset_count, -1)
            @ model.base.null.T
            if model.group_clock_count
            else None
        ),
    )
    actual = state.predict(
        observations.times_s, observations.rf_hz, observations.receiver, observations.channel >= 5
    )
    expected = model.correction(fit["vector"], fit["nuisance"])
    np.testing.assert_allclose(actual, expected, atol=1e-6, rtol=0)
    return state
