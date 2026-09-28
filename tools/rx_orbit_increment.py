"""Attach a causal orbit-increment signal kernel to referenced geometry lanes."""

from __future__ import annotations

import math

import numpy as np

from tools.rx_causal_frequency import _wrapped_phase_density
from tools.rx_causal_geometry import attach_causal_frequency

BIRTH_WEIGHT = 0.2
OBSERVATION_SIGMA_HZ = 500.0
ACCELERATION_SD_HZ_S = 500.0
MAX_HISTORY_AGE_S = 10.0


def _wrapped(value, period):
    return np.remainder(value + period / 2.0, period) - period / 2.0


def _history_points(values, period):
    wrapped = np.remainder(np.asarray(values, dtype=float), period)
    return np.asarray(sorted(set(wrapped.tolist())), dtype=float)


def _target_density(points, means, sigma, period):
    points = np.asarray(points, dtype=float)
    means = np.asarray(means, dtype=float)
    density = np.full(len(points), BIRTH_WEIGHT, dtype=float)
    if len(means):
        signal = np.zeros(len(points), dtype=float)
        for mean in means:
            signal += _wrapped_phase_density(points, mean, sigma, period)
        density += (1.0 - BIRTH_WEIGHT) * signal / len(means)
    if np.any(~np.isfinite(density)) or np.any(density <= 0):
        raise ArithmeticError("target phase density must be finite and positive")
    return density


def attach_orbit_increment(lanes, motion_control=None, frequency_shift_fraction=0.0):
    """Replace signal ratios while retaining the exact causal-reference density."""
    if motion_control not in (None, "zero", "reverse"):
        raise ValueError("motion_control must be None, zero, or reverse")
    if not math.isfinite(float(frequency_shift_fraction)):
        raise ValueError("frequency_shift_fraction must be finite")
    causal, reference_diagnostics = attach_causal_frequency(lanes)
    output, diagnostics = [], []
    for lane_index, lane in enumerate(causal):
        changed = {**lane, "signal": lane["signal"].copy()}
        period = float(lane["source"]["alias_period_hz"])
        raw_components = lane["source"].get("components", [])
        if (
            len(raw_components) < 2
            or raw_components[-1].get("kind") != "other"
            or any(component.get("kind") != "track_candidate" for component in raw_components[:-1])
        ):
            raise ValueError("components must be track candidates followed by other")
        components = raw_components[:-1]
        nominee_keys = [
            (component.get("track_id"), component.get("catalog_number")) for component in components
        ]
        if (
            any(None in key for key in nominee_keys)
            or len(nominee_keys) != changed["signal"].shape[1]
            or len(nominee_keys) != len(set(nominee_keys))
        ):
            raise ValueError("nominee keys do not match signal dimension uniquely")
        receiver_rows = []
        for receiver_index, receiver in enumerate(("rx0", "rx1")):
            history = None
            clock = None
            window_rows = []
            reference_windows = reference_diagnostics[lane_index]["receivers"][receiver_index][
                "windows"
            ]
            for local_index, (source_index, reference_row) in enumerate(
                zip(lane["indices"], reference_windows, strict=True)
            ):
                window = lane["source"]["windows"][source_index]
                time_s = float(lane["times"][local_index])
                if not math.isfinite(time_s) or (clock is not None and time_s <= clock):
                    raise ValueError("lane times must be finite and strictly increasing")
                clock = time_s
                predictions = window.get("predictions", [])
                prediction_keys = [
                    (prediction.get("track_id"), prediction.get("catalog_number"))
                    for prediction in predictions
                ]
                if prediction_keys != nominee_keys:
                    raise ValueError("prediction keys/order do not match nominees")
                current_mu = np.asarray(
                    [prediction.get("mu_canonical_rx0_hz") for prediction in predictions],
                    dtype=float,
                )
                if np.any(~np.isfinite(current_mu)):
                    raise ValueError("nominee frequencies must be finite")
                observed = np.asarray(
                    [candidate["canonical_rx0_hz"] for candidate in window["observed"][receiver]],
                    dtype=float,
                )
                if observed.ndim != 1 or np.any(~np.isfinite(observed)):
                    raise ValueError("observed frequencies must be finite and one-dimensional")
                phase_density = np.asarray(reference_row["phase_density"], dtype=float)
                if phase_density.shape != observed.shape or np.any(phase_density <= 0):
                    raise ValueError("causal reference receipt does not match observations")
                recent = history is not None and time_s - history["time_s"] <= MAX_HISTORY_AGE_S
                nominee_rows = []
                for nominee_index, key in enumerate(nominee_keys):
                    if recent:
                        horizon = time_s - history["time_s"]
                        delta = float(
                            _wrapped(
                                current_mu[nominee_index] - history["mu"][nominee_index],
                                period,
                            )
                        )
                        if motion_control == "zero":
                            delta = 0.0
                        elif motion_control == "reverse":
                            delta = -delta
                        means = history["points"] + delta
                        sigma = math.sqrt(
                            2.0 * OBSERVATION_SIGMA_HZ**2
                            + (ACCELERATION_SD_HZ_S * horizon) ** 2
                        )
                        mode = "orbit_increment"
                    else:
                        horizon = None
                        delta = None
                        means = np.asarray([current_mu[nominee_index]])
                        sigma = OBSERVATION_SIGMA_HZ
                        mode = "frozen_mu"
                    means = np.remainder(
                        means + float(frequency_shift_fraction) * period, period
                    )
                    target = _target_density(observed, means, sigma, period)
                    changed["signal"][local_index, nominee_index, receiver_index] = float(
                        np.sum(target / phase_density)
                    )
                    nominee_rows.append(
                        {
                            "track_id": key[0],
                            "catalog_number": key[1],
                            "mode": mode,
                            "history_source_window_id": (
                                None if not recent else history["source_window_id"]
                            ),
                            "history_time_s": None if not recent else history["time_s"],
                            "forecast_horizon_s": horizon,
                            "motion_delta_hz": delta,
                            "target_means_hz": means.tolist(),
                            "sigma_hz": sigma,
                        }
                    )
                window_rows.append(
                    {
                        "source_window_id": window["source_window_id"],
                        "role": window["role"],
                        "candidate_count": len(observed),
                        "reference_receipt": reference_row,
                        "nominee_keys": [
                            {"track_id": key[0], "catalog_number": key[1]}
                            for key in nominee_keys
                        ],
                        "delta_mu_hz": [row["motion_delta_hz"] for row in nominee_rows],
                        "target_sigma_hz": [row["sigma_hz"] for row in nominee_rows],
                        "nominees": nominee_rows,
                    }
                )
                if len(observed):
                    history = {
                        "source_window_id": window["source_window_id"],
                        "time_s": time_s,
                        "points": _history_points(observed, period),
                        "mu": current_mu.copy(),
                    }
            receiver_rows.append({"receiver": receiver, "windows": window_rows})
        output.append(changed)
        diagnostics.append(
            {
                "lane": lane["source"]["lane"],
                "settings": {
                    "uniform_birth_weight": BIRTH_WEIGHT,
                    "observation_sigma_hz": OBSERVATION_SIGMA_HZ,
                    "acceleration_sd_hz_s": ACCELERATION_SD_HZ_S,
                    "max_history_age_s": MAX_HISTORY_AGE_S,
                    "motion_control": motion_control,
                    "frequency_shift_fraction": float(frequency_shift_fraction),
                },
                "receivers": receiver_rows,
            }
        )
    return output, diagnostics
