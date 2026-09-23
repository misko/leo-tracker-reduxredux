#!/usr/bin/env python3
"""Small, truth-labelled local observability calculation for the phase audit.

This is deliberately an algebraic sensitivity demonstration, not a fit to IQ
or an assertion about the current station geometry.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


OUT = Path(__file__).resolve().parent / "results.json"
C = 299_792_458.0
RF_HZ = 11_440_312_500.0
BASELINE_M = 0.08


def unit(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


def rank_summary(matrix: np.ndarray, names: list[str]) -> dict:
    singular = np.linalg.svd(matrix, compute_uv=False)
    rank = int(np.linalg.matrix_rank(matrix, tol=1e-10))
    _, _, vt = np.linalg.svd(matrix)
    null = vt[rank:].tolist()
    return {
        "matrix": matrix.tolist(),
        "parameter_names": names,
        "rank": rank,
        "singular_values": singular.tolist(),
        "right_nullspace_basis": null,
    }


def main() -> None:
    # Explicit local truth: line of sight and receiver-relative velocity in a
    # fixture/world frame.  The baseline is aligned with x.
    u = unit(np.array([0.35, -0.20, 0.915]))
    b = np.array([BASELINE_M, 0.0, 0.0])
    v = np.array([1500.0, 6200.0, -1100.0])
    tangent = np.eye(3) - np.outer(u, u)
    k = 2 * np.pi * RF_HZ / C
    geometric_phase_rad = float(k * b @ u)
    phase_rate_hz = float((RF_HZ / C) * b @ tangent @ v / 500_000.0)
    doppler_projection_m_s = float(u @ v)

    # Rows are normalized physical projections.  Doppler observes u^T v;
    # phase-rate observes b^T(I-uu^T)v.  A single baseline therefore leaves
    # one velocity direction unobserved even with perfect calibration.
    radial = u[None, :]
    transverse = (b @ tangent)[None, :]
    velocity_two_projection = np.vstack((radial, transverse))
    # Giving phase rate a free receiver-rate nuisance makes its single-row
    # geometric contribution collinear with that nuisance and removes it.
    velocity_with_rate_nuisance = np.array(
        [[*u, 0.0], [*(b @ tangent), 1.0]], dtype=float
    )
    nuisance = velocity_with_rate_nuisance[:, 3:]
    projected = velocity_with_rate_nuisance[:, :3] - nuisance @ np.linalg.pinv(nuisance) @ velocity_with_rate_nuisance[:, :3]

    # Each source parameter is its dimensionless direction cosine projected
    # onto this x-aligned baseline.  This avoids assigning an unprovided local
    # tangent basis to either source. One static source phase has one equation;
    # two sources at one time cancel the common electrical phase only in their
    # difference, still yielding one scalar directional-separation projection.
    direction_single = np.array([[k * BASELINE_M, 1.0]])
    direction_two_sources = np.array(
        [[k * BASELINE_M, 0.0, 1.0], [0.0, k * BASELINE_M, 1.0]]
    )
    source_difference = np.array([[k * BASELINE_M, -k * BASELINE_M]])

    document = {
        "kind": "synthetic_phase_geometry_local_observability_v1",
        "scope": "explicit simulated truth; no saved-IQ values or measured station calibration",
        "truth": {
            "rf_hz": RF_HZ,
            "baseline_m": b.tolist(),
            "range_m": 500000.0,
            "line_of_sight_unit": u.tolist(),
            "relative_velocity_m_s": v.tolist(),
            "geometric_phase_rad_modulo_2pi": float(np.angle(np.exp(1j * geometric_phase_rad))),
            "geometric_phase_rate_hz": phase_rate_hz,
            "radial_velocity_projection_m_s": doppler_projection_m_s,
        },
        "cases": {
            "calibrated_single_baseline_phase_plus_doppler_velocity": rank_summary(
                velocity_two_projection, ["vx_m_s", "vy_m_s", "vz_m_s"]
            ),
            "same_velocity_with_free_phase_rate_nuisance": rank_summary(
                projected, ["vx_m_s", "vy_m_s", "vz_m_s"]
            ),
            "single_source_direction_with_free_electrical_phase": rank_summary(
                direction_single,
                ["baseline_projected_direction_cosine", "electrical_phase_rad"],
            ),
            "two_simultaneous_sources_shared_electrical_phase": rank_summary(
                direction_two_sources,
                [
                    "source_a_baseline_projected_direction_cosine",
                    "source_b_baseline_projected_direction_cosine",
                    "electrical_phase_rad",
                ],
            ),
            "two_source_difference_after_common_phase_cancellation": rank_summary(
                source_difference,
                [
                    "source_a_baseline_projected_direction_cosine",
                    "source_b_baseline_projected_direction_cosine",
                ],
            ),
        },
        "interpretation": [
            "The calibrated single-baseline plus Doppler case has rank two for three velocity components; it cannot recover total speed or a 3D velocity vector.",
            "A free phase-rate nuisance absorbs the only transverse projection in this two-row toy problem, leaving the radial projection only.",
            "A same-time two-source difference cancels only a common, frequency-matched electrical phase. It constrains a relative projected direction, not either absolute direction or range.",
        ],
    }
    expected_ranks = {
        "calibrated_single_baseline_phase_plus_doppler_velocity": 2,
        "same_velocity_with_free_phase_rate_nuisance": 1,
        "single_source_direction_with_free_electrical_phase": 1,
        "two_simultaneous_sources_shared_electrical_phase": 2,
        "two_source_difference_after_common_phase_cancellation": 1,
    }
    observed_ranks = {name: result["rank"] for name, result in document["cases"].items()}
    assert observed_ranks == expected_ranks, (observed_ranks, expected_ranks)
    OUT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
