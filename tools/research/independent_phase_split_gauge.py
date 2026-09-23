"""Conditional split-symbol frequency gauge, fixed from calibration-even data."""

import math

from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S

FOLD_PERIOD_HZ = 1 / (2 * OFDM_SYMBOL_DURATION_S)
CALIBRATION_GROUPS = (0, 3, 5)
RESPONSE_GROUPS = (1, 2, 4)


def acquired_only(row):
    if row["branches"][0]["seed_cfo_hz"] != row["observation"]["acquired_cfo_hz"]:
        raise ValueError("first branch is not the bound acquired seed")
    return {**row, "branches": [row["branches"][0]], "selected_seed_index": 0}


def circular_response(row):
    """Acquired-only response with no archived GLRT gauge or alias selection."""
    row = acquired_only(row)
    observation = row["observation"]
    frames = [
        item
        for item in row["branches"][0]["frames"]
        if item["group_id"] in RESPONSE_GROUPS
        and item["frame"]["training_supported"]
        and item["frame"]["odd"] is not None
    ]
    return {
        "visit_index": observation["visit_index"],
        "observation_time_s": observation["time_s"],
        "period_hz": FOLD_PERIOD_HZ * observation["rf_normalization_scale"],
        "time_s": [item["session_time_s"] for item in frames],
        "observed_hz": [
            item["frame"]["odd"]["absolute_cfo_hz"] * observation["rf_normalization_scale"]
            for item in frames
        ],
        "frame_count": len(frames),
        "odd_search_boundary_count": sum(
            item["frame"]["odd"]["search_boundary"] for item in frames
        ),
        "abstention_reason": "no_eligible_odd_response" if not frames else None,
    }


def calibration_gauge(row):
    """Fix a whole-dwell lattice integer without inspecting odd measurements.

    This inherits the archived source's coarse frequency gauge. It does not
    identify the physical source or prove raw-IQ equivalence of different NCOs.
    """
    observation = row["observation"]
    branch = row["branches"][row["selected_seed_index"]]
    frames = [
        item
        for item in branch["frames"]
        if item["group_id"] in CALIBRATION_GROUPS
        and item["frame"]["training_supported"]
        and item["frame"]["even"] is not None
        and not item["frame"]["even"]["search_boundary"]
    ]
    if not frames:
        return None
    mean = sum(item["frame"]["even"]["absolute_cfo_hz"] for item in frames) / len(frames)
    target = observation["dealiased_native_cfo_hz"]
    if not math.isfinite(mean) or not math.isfinite(target):
        raise ValueError("nonfinite calibration gauge")
    integer = round((target - mean) / FOLD_PERIOD_HZ)
    return {
        "alias_lift_index": integer,
        "fold_period_hz": FOLD_PERIOD_HZ,
        "calibration_frame_count": len(frames),
        "native_even_mean_hz": mean,
        "native_closure_hz": mean + integer * FOLD_PERIOD_HZ - target,
        "normalized_even_mean_hz": (mean + integer * FOLD_PERIOD_HZ)
        * observation["rf_normalization_scale"],
        "time_s": sum(item["session_time_s"] for item in frames) / len(frames),
    }


def phase_cfo(row):
    gauge = calibration_gauge(row)
    if gauge is None:
        raise ValueError("training dwell lacks calibration-even support")
    return gauge["normalized_even_mean_hz"], gauge["time_s"]


def odd_response(row):
    observation = row["observation"]
    gauge = calibration_gauge(row)
    branch = row["branches"][row["selected_seed_index"]]
    frames = (
        []
        if gauge is None
        else [
            item
            for item in branch["frames"]
            if item["group_id"] in RESPONSE_GROUPS
            and item["frame"]["training_supported"]
            and item["frame"]["odd"] is not None
        ]
    )
    return {
        "visit_index": observation["visit_index"],
        "observation_time_s": observation["time_s"],
        "gauge": gauge,
        "time_s": [item["session_time_s"] for item in frames],
        "observed_hz": [
            (item["frame"]["odd"]["absolute_cfo_hz"] + gauge["alias_lift_index"] * FOLD_PERIOD_HZ)
            * observation["rf_normalization_scale"]
            for item in frames
        ],
        "frame_count": len(frames),
        "odd_search_boundary_count": sum(
            item["frame"]["odd"]["search_boundary"] for item in frames
        ),
        "abstention_reason": "no_calibration_even_support"
        if gauge is None
        else ("no_eligible_odd_response" if not frames else None),
    }
