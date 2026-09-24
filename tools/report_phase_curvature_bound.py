#!/usr/bin/env python3
"""Conditional circular-orbit curvature check of a saved DD trajectory."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from leo.contracts.digests import canonical_json_bytes, sha256_digest

C = 299_792_458.0
R = 6_378_137.0
MU = 3.986004418e14
OMEGA = 7.2921150e-5


def circular_bounds(altitude_m: float, baseline_m: float, rf_hz: float) -> tuple[float, float]:
    """Return single-source |phase'| and |phase''| bounds, degrees/s and /s².

    Spherical Earth, fixed ground baseline, circular orbit, fixed RF carrier.
    Observer radius is bounded by R (the recorded site is below this radius).
    """
    if not all(math.isfinite(x) and x > 0 for x in (altitude_m, baseline_m, rf_hz)):
        raise ValueError("positive finite altitude, baseline and RF required")
    radius = R + altitude_m
    speed = math.sqrt(MU / radius) + OMEGA * R
    acceleration = MU / radius**2 + OMEGA**2 * R
    phase_scale = 360 * rf_hz * baseline_m / C
    rate = phase_scale * (speed / altitude_m + OMEGA)
    curvature = phase_scale * (
        acceleration / altitude_m
        + 3 * (speed / altitude_m) ** 2
        + 2 * OMEGA * speed / altitude_m
        + OMEGA**2
    )
    return rate, curvature


def interpolation_residual(times: list[float], phases: list[float]) -> tuple[float, float]:
    """Return central residual and its multiplier for a |phase''| bound."""
    if len(times) != 3 or len(phases) != 3 or not times[0] < times[1] < times[2]:
        raise ValueError("three increasing times and phases required")
    left, right = times[1] - times[0], times[2] - times[1]
    predicted = (right * phases[0] + left * phases[2]) / (left + right)
    return phases[1] - predicted, left * right / 2


def run(document: dict) -> dict:
    path = set(document["fixed_phase_blind_path_visit_indexes"])
    rows = sorted(
        (r for r in document["rows"] if r["visit_index"] in path
         and r["state"] == "accepted_matched_pilot_double_difference"),
        key=lambda r: r["exact_time_s"],
    )
    # Explicit largest illustrated baseline and fastest illustrated circular orbit.
    baseline = 0.080 + 2 * 0.100 * math.sin(math.radians(10))
    rate, curvature = circular_bounds(350_000, baseline, 11_459_687_500)
    dd_rate, dd_curvature = 2 * rate, 2 * curvature
    phases = [r["wrapped_high_minus_low_deg"] for r in rows]
    # Verify that an alternative ±360-degree step cannot satisfy this rate bound.
    for a, b, pa, pb in zip(rows[:-1], rows[1:], phases[:-1], phases[1:], strict=True):
        maximum_change = dd_rate * (b["exact_time_s"] - a["exact_time_s"])
        if abs(pb - pa) > maximum_change or 360 - abs(pb - pa) <= maximum_change:
            raise ValueError("point-phase branch is inconsistent or ambiguous under rate bound")
    triplets = []
    for i in range(1, len(rows) - 1):
        selected = rows[i - 1:i + 2]
        times = [r["exact_time_s"] for r in selected]
        residual, multiplier = interpolation_residual(times, phases[i - 1:i + 2])
        bound = multiplier * dd_curvature
        # If each point has bounded error e, interpolation residual can shift by <=2e.
        minimum_uniform_point_error = max(0.0, abs(residual) - bound) / 2
        triplets.append({
            "visit_indexes": [r["visit_index"] for r in selected],
            "time_gaps_s": [times[1] - times[0], times[2] - times[1]],
            "central_interpolation_residual_deg": residual,
            "geometric_interpolation_bound_deg": bound,
            "minimum_uniform_point_error_deg": minimum_uniform_point_error,
        })
    result = {
        "schema_version": 1,
        "input_evidence_sha256": document["evidence_sha256"],
        "session_id": document["session_id"],
        "baseline_m_scenario_not_measurement": baseline,
        "circular_orbit_altitude_m": 350_000,
        "fixed_carrier_hz": 11_459_687_500,
        "single_source_rate_bound_deg_s": rate,
        "two_source_rate_bound_deg_s": dd_rate,
        "two_source_curvature_bound_deg_s2": dd_curvature,
        "point_phase_interpretation_conditional": True,
        "unknown_channel_terms_or_finite_window_bias_not_excluded": True,
        "geometric_phase_recovered": False,
        "triplets": triplets,
    }
    result["evidence_sha256"] = sha256_digest(canonical_json_bytes(result))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.input.read_text())
    body = {k: v for k, v in document.items() if k != "evidence_sha256"}
    if sha256_digest(canonical_json_bytes(body)) != document["evidence_sha256"]:
        raise ValueError("input canonical digest mismatch")
    result = run(document)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
