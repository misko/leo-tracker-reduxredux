"""Checks for scientific controls and fixed recommendation behavior."""

import numpy as np
from simulation import (
    BASELINES,
    CONFIG,
    NATURAL_CANDIDATES,
    PRIMARY_PHASE_SCENARIOS,
    SCENARIOS,
    UNION_MEMBERS,
    add_union,
    choose_recommendation,
    draw_case,
    paired_interval,
    prior,
)


def test_signal_and_control_use_same_iq_and_common_fourteen_frame_cfo():
    geometry = prior.pilot_geometry()
    null_exact, null_control, _ = draw_case(
        np.random.default_rng(44), 5, SCENARIOS["coherent"], geometry
    )
    exact, control, truth = draw_case(
        np.random.default_rng(44), 5, SCENARIOS["coherent"], geometry, 0
    )
    signal = exact - null_exact
    assert signal.shape == (5, 14, 64)
    np.testing.assert_allclose(np.abs(signal), 1)
    np.testing.assert_allclose(control - null_control, geometry["overlap"] * signal)
    increments = signal[:, :, 1:] * np.conj(signal[:, :, :-1])
    expected = np.exp(2j * np.pi * truth * CONFIG["symbol_step_s"])
    np.testing.assert_allclose(increments, np.broadcast_to(expected[:, None, None], (5, 14, 63)))


def test_rare_pi_jump_has_zero_or_one_jump_per_frame_at_prespecified_rate():
    geometry = prior.pilot_geometry()
    null, _, _ = draw_case(np.random.default_rng(63), 200, SCENARIOS["rare_pi_jump"], geometry)
    exact, _, truth = draw_case(
        np.random.default_rng(63), 200, SCENARIOS["rare_pi_jump"], geometry, 0
    )
    signal = exact - null
    coherent_increment = np.exp(2j * np.pi * truth[:, None, None] * CONFIG["symbol_step_s"])
    jump = np.abs(signal[:, :, 1:] * signal[:, :, :-1].conj() / coherent_increment - 1) > 1
    assert np.all(jump.sum(axis=2) <= 1)
    assert 0.22 < np.mean(jump.sum(axis=2)) < 0.28


def test_union_selects_cfo_of_standardized_winner_and_hybrid_uses_coherent_cfo():
    scores = {}
    values = [[1, 3], [5, 1], [2, 4]]
    for index, member in enumerate(UNION_MEMBERS):
        scores[member] = {"score": np.array(values[index]),
                          "cfo_hz": np.array([index * 10, index * 10 + 1]),
                          "control_cfo_hz": np.zeros(2)}
    scores["gaussian_coherent"] = {"cfo_hz": np.array([701, 702])}
    normalization = {member: {"mean": 0, "std": 1} for member in UNION_MEMBERS}
    result = add_union(scores, normalization)
    np.testing.assert_array_equal(result["multiscale_union"]["score"], [5, 4])
    np.testing.assert_array_equal(result["multiscale_union"]["cfo_hz"], [10, 21])
    np.testing.assert_array_equal(result["multiscale_union_cfo64"]["cfo_hz"], [701, 702])


def development_fixture(candidate_detection):
    methods = dict.fromkeys((*NATURAL_CANDIDATES, *BASELINES))
    development = {
        scenario: {str(snr): {method: {"joint_rate": 0.2, "detection_rate": 0.8}
                              for method in methods} for snr in CONFIG["snr_db"]}
        for scenario in ("coherent", *PRIMARY_PHASE_SCENARIOS)
    }
    for candidate in NATURAL_CANDIDATES:
        development["coherent"]["-15"][candidate]["detection_rate"] = candidate_detection
    return development


def test_selection_can_recommend_none_and_enforces_both_baselines():
    development = development_fixture(0.74)
    assert choose_recommendation(development)["selected"] is None
    development = development_fixture(0.76)
    development["coherent"]["-15"]["current_coherent_margin"]["detection_rate"] = 0.83
    assert choose_recommendation(development)["selected"] is None
    development["coherent"]["-15"]["current_coherent_margin"]["detection_rate"] = 0.80
    for scenario in PRIMARY_PHASE_SCENARIOS:
        for snr in CONFIG["snr_db"]:
            development[scenario][str(snr)]["phase_kernel32"]["joint_rate"] = 0.30
    assert choose_recommendation(development)["selected"] == "phase_kernel32"


def test_paired_interval_uses_shared_trials_and_exact_identity():
    events = np.array([True, False, True, True])
    result = paired_interval(events, events, np.random.default_rng(42), replicates=100)
    assert result["difference"] == 0
    assert result["bootstrap_95"] == [0, 0]
    assert result["selected_only"] == result["baseline_only"] == 0
