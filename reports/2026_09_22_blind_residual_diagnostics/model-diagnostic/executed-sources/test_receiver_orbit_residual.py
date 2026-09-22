import numpy as np

from leo.analysis.research.receiver_orbit_residual import (
    ResidualCandidate,
    ResidualDiagnosticConfig,
    ResidualEpisode,
    diagnose_receiver_orbit_residuals,
)


def episode(
    name,
    receiver,
    norad,
    *,
    receiver_slope=0.0,
    satellite_rate=0.0,
    design_scale=4000.0,
    heldout_poison=0.0,
):
    time_s = np.linspace(0, 3600, 20)
    training = np.arange(20) < 12
    time_h = (time_s - time_s[training].mean()) / 3600
    design = design_scale * time_h * (1.0 + 0.1 * int(norad % 3))
    residual = receiver_slope * time_h + satellite_rate * design
    residual = residual.copy()
    residual[~training] += heldout_poison
    return ResidualEpisode(
        episode_id=name,
        receiver_drift_group=receiver,
        time_s=time_s,
        training=training,
        candidates=(ResidualCandidate(norad, 0.9, residual, design),),
        null_probability=0.05,
        omitted_probability_mass=0.05,
    )


def model(result, name):
    return next(item for item in result.models if item.model == name)


def test_recovers_receiver_frequency_drift_and_scores_heldout():
    episodes = (
        episode("a", "rx0", 101, receiver_slope=180),
        episode("b", "rx0", 202, receiver_slope=180),
        episode("c", "rx1", 101, receiver_slope=-90),
        episode("d", "rx1", 202, receiver_slope=-90),
    )
    result = diagnose_receiver_orbit_residuals(
        episodes, ResidualDiagnosticConfig(receiver_slope_sigma_hz_h=5000)
    )
    receiver = model(result, "receiver_drift")
    np.testing.assert_allclose(receiver.receiver_slopes_normalized_hz_h["rx0"], 180, atol=8)
    np.testing.assert_allclose(receiver.receiver_slopes_normalized_hz_h["rx1"], -90, atol=8)
    assert receiver.heldout_loss < model(result, "offset_only").heldout_loss


def test_recovers_recurrent_satellite_specific_proxy():
    episodes = (
        episode("a", "rx0", 101, satellite_rate=0.06),
        episode("b", "rx1", 101, satellite_rate=0.06),
        episode("c", "rx0", 202, satellite_rate=-0.04),
        episode("d", "rx1", 202, satellite_rate=-0.04),
    )
    result = diagnose_receiver_orbit_residuals(
        episodes, ResidualDiagnosticConfig(satellite_rate_sigma_unit=0.5)
    )
    satellite = model(result, "satellite_proxy")
    np.testing.assert_allclose(satellite.satellite_rates[101], 0.06, atol=0.012)
    np.testing.assert_allclose(satellite.satellite_rates[202], -0.04, atol=0.012)
    assert satellite.heldout_loss < model(result, "offset_only").heldout_loss
    assert result.recurring_satellites == {101: 2, 202: 2}


def test_heldout_values_do_not_change_fit():
    clean = (episode("a", "rx0", 101, receiver_slope=150),)
    poisoned = (episode("a", "rx0", 101, receiver_slope=150, heldout_poison=10000),)
    left = model(diagnose_receiver_orbit_residuals(clean), "joint")
    right = model(diagnose_receiver_orbit_residuals(poisoned), "joint")
    assert left.receiver_slopes_normalized_hz_h == right.receiver_slopes_normalized_hz_h
    assert left.satellite_rates == right.satellite_rates
    assert right.heldout_loss > left.heldout_loss


def test_reports_exact_receiver_satellite_design_confounding():
    # One satellite is seen only on one receiver and its proxy is proportional
    # to time, so the two explanatory columns are observationally identical.
    result = diagnose_receiver_orbit_residuals((episode("a", "rx0", 101),))
    assert result.design_rank < result.design_columns
    assert result.maximum_receiver_satellite_correlation > 0.999
    assert "receiver-satellite-design-rank-deficient" in result.reasons
    assert "receiver-satellite-design-highly-confounded" in result.reasons
    assert "no-satellite-support-recurs-across-episodes" in result.reasons


def test_rejects_probability_mass_over_one():
    item = episode("a", "rx0", 101)
    bad = ResidualEpisode(
        item.episode_id,
        item.receiver_drift_group,
        item.time_s,
        item.training,
        (ResidualCandidate(101, 0.96, np.zeros(20), np.zeros(20)),),
        0.05,
        0.05,
    )
    with np.testing.assert_raises_regex(ValueError, "probability exceeds"):
        diagnose_receiver_orbit_residuals((bad,))


def test_zero_weight_candidate_does_not_create_a_rank_column():
    item = episode("a", "rx0", 101)
    candidate = item.candidates[0]
    with_zero = ResidualEpisode(
        item.episode_id,
        item.receiver_drift_group,
        item.time_s,
        item.training,
        item.candidates
        + (
            ResidualCandidate(
                999,
                0.0,
                candidate.residual_hz,
                candidate.satellite_design_hz_per_unit,
            ),
        ),
        item.null_probability,
        item.omitted_probability_mass,
    )
    result = diagnose_receiver_orbit_residuals((with_zero,))
    satellite = model(result, "satellite_proxy")
    assert set(satellite.satellite_rates) == {101}
    assert result.design_columns == 2
