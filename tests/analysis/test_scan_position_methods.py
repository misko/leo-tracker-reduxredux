import json

import numpy as np

from leo.analysis.research.formal_orbit import doppler_hz
from leo.analysis.research.regional_doppler import Region
from leo.analysis.scan_position_methods import (
    ScanPositionEpisode,
    fit_expanded_pass_balanced_doppler,
    fit_joint_position_orbit_corrections,
    fit_soft_identity_mixture,
)


def _episodes(heldout_shift=0.0, injected_rate=0.0, quartic=False):
    region = Region(40.0, -75.0, 160, 160)
    receiver = region.points([13.0], [-9.0]).ecef_km[0]
    episodes = []
    for track in range(4):
        n = 20
        theta = np.linspace(0.2 + track, 1.4 + track, n)
        p = np.column_stack(
            (7000 * np.cos(theta), 7000 * np.sin(theta), 900 + 500 * np.sin(2 * theta))
        )
        v = np.column_stack((-5 * np.sin(theta), 5 * np.cos(theta), np.cos(2 * theta)))
        wrong_p = np.roll(p, 5, axis=0)
        wrong_v = np.roll(v, 5, axis=0)
        training = np.arange(n) % 4 != 3
        dp = np.column_stack((8 * np.sin(theta), -5 * np.cos(theta), np.full(n, 3.0)))
        dv = np.column_stack((0.02 * np.cos(theta), 0.03 * np.sin(theta), np.full(n, -0.01)))
        phase_s = 12.0 * injected_rate
        corrected_p = p + dp * phase_s
        corrected_v = v + dv * phase_s
        y = doppler_hz(receiver, corrected_p, corrected_v) + 100 * (track + 1)
        y = y + np.where(training, 0.0, heldout_shift)
        outer = (
            {
                "phase_position_minus2_ecef_km": np.stack((p - 2 * dp, wrong_p - 2 * dp)),
                "phase_velocity_minus2_ecef_km_s": np.stack((v - 2 * dv, wrong_v - 2 * dv)),
                "phase_position_plus2_ecef_km": np.stack((p + 2 * dp, wrong_p + 2 * dp)),
                "phase_velocity_plus2_ecef_km_s": np.stack((v + 2 * dv, wrong_v + 2 * dv)),
            }
            if quartic
            else {}
        )
        episodes.append(
            ScanPositionEpisode(
                f"t{track}",
                f"pass{track // 2}",
                np.asarray([f"{track}:{i}" for i in range(n)]),
                y,
                training,
                np.arange(n, dtype=float),
                np.asarray([100 + track, 900 + track]),
                np.stack((p, wrong_p)),
                np.stack((v, wrong_v)),
                1000,
                orbit_age_h=np.full((2, n), 12.0),
                phase_position_minus_ecef_km=np.stack((p - dp, wrong_p - dp)),
                phase_velocity_minus_ecef_km_s=np.stack((v - dv, wrong_v - dv)),
                phase_position_plus_ecef_km=np.stack((p + dp, wrong_p + dp)),
                phase_velocity_plus_ecef_km_s=np.stack((v + dv, wrong_v + dv)),
                **outer,
            )
        )
    return episodes, region


def test_pass_balanced_fit_is_blind_to_evaluation_values():
    episodes, region = _episodes()
    changed, _ = _episodes(1_000_000.0)
    a = fit_expanded_pass_balanced_doppler(episodes, region)
    b = fit_expanded_pass_balanced_doppler(changed, region)
    assert np.hypot(a["east_km"] - 13, a["north_km"] + 9) < 1.0
    np.testing.assert_allclose(
        [a["east_km"], a["north_km"]], [b["east_km"], b["north_km"]], atol=1e-7
    )
    assert a["diagnostics"]["pass_count"] == 2
    assert b["evaluation_rms_hz"] > 100_000


def test_soft_mixture_uses_candidate_support_and_training_only():
    episodes, region = _episodes()
    changed, _ = _episodes(1_000_000.0)
    a = fit_soft_identity_mixture(episodes, region)
    b = fit_soft_identity_mixture(changed, region)
    assert set(a["modes"]["candidate_id"]) == {"100", "101", "102", "103"}
    assert np.hypot(a["east_km"] - 13, a["north_km"] + 9) < 1.0
    np.testing.assert_allclose(
        [a["east_km"], a["north_km"]], [b["east_km"], b["north_km"]], atol=1e-7
    )
    assert "not a calibrated" in a["diagnostics"]["correlation_warning"]


def test_joint_orbit_method_reports_pending_exact_replay():
    episodes, region = _episodes(injected_rate=0.03, quartic=True)
    changed, _ = _episodes(heldout_shift=1_000_000.0, injected_rate=0.03, quartic=True)
    result = fit_joint_position_orbit_corrections(episodes, region)
    changed_result = fit_joint_position_orbit_corrections(changed, region)
    assert np.isfinite(result["latitude_deg"])
    assert result["diagnostics"]["exact_correction_replay"] == "pending"
    assert result["diagnostics"]["phase_interpolation"] == "quartic_5_point"
    assert set(result["diagnostics"]["rate_corrections_s_h"]) == {"100", "101", "102", "103"}
    assert result["training_point_count"] == 60
    np.testing.assert_allclose(
        [result["east_km"], result["north_km"]],
        [changed_result["east_km"], changed_result["north_km"]],
        atol=1e-7,
    )
    np.testing.assert_allclose(
        list(result["diagnostics"]["rate_corrections_s_h"].values()), 0.03, atol=3e-3
    )


def test_empty_inputs_report_insufficient_and_results_are_json_ready():
    _, region = _episodes()
    empty = fit_expanded_pass_balanced_doppler([], region)
    assert empty["state"] == "insufficient"
    episodes, _ = _episodes()
    results = (
        fit_expanded_pass_balanced_doppler(episodes, region),
        fit_joint_position_orbit_corrections(episodes, region),
        fit_soft_identity_mixture(episodes, region),
    )
    for result in results:
        json.dumps(result, allow_nan=False)
