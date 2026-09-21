import numpy as np

from leo.analysis.research.identity_mixture import (
    MixtureConfig,
    mixture_statistics,
    profile_offsets,
)


def test_profiled_offsets_are_frozen_from_training() -> None:
    segment = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    training = np.array([True, True, False, False] * 2)
    residual = np.array([10.0, 14.0, 100.0, 104.0, -4.0, 4.0, 80.0, 88.0])
    centered, offsets = profile_offsets(residual, segment, training)
    np.testing.assert_allclose(offsets, [12.0, 0.0])
    np.testing.assert_allclose(centered, [-2.0, 2.0, 88.0, 92.0, -4.0, 4.0, 80.0, 88.0])


def test_heldout_values_do_not_change_training_posterior() -> None:
    segment = np.zeros(8, dtype=int)
    training = np.array([True, False] * 4)
    residual = np.array([[0.0, 1.0, 0.0, 2.0, 0.0, 3.0, 0.0, 4.0], [50.0] * 8])
    first = mixture_statistics(residual, np.arange(8.0), segment, training, 100)
    changed = residual.copy()
    changed[:, ~training] += 100_000
    second = mixture_statistics(changed, np.arange(8.0), segment, training, 100)
    np.testing.assert_allclose(first["candidate_posterior"], second["candidate_posterior"])
    assert first["train_log_evidence"] == second["train_log_evidence"]
    assert first["heldout_log_predictive"] != second["heldout_log_predictive"]


def test_full_catalogue_prior_is_not_renormalized_to_shortlist() -> None:
    segment = np.zeros(8, dtype=int)
    training = np.array([True, False] * 4)
    residual = np.zeros((1, 8))
    small = mixture_statistics(residual, np.arange(8.0) * 1000, segment, training, 10)
    large = mixture_statistics(residual, np.arange(8.0) * 1000, segment, training, 10_000)
    assert small["train_log_evidence"] > large["train_log_evidence"]


def test_unassigned_component_handles_impossible_or_outlying_candidates() -> None:
    segment = np.zeros(8, dtype=int)
    training = np.array([True, False] * 4)
    residual = np.array([[0.0, 0.0, 500_000.0, 0.0, -500_000.0, 0.0, 500_000.0, 0.0]])
    result = mixture_statistics(
        residual,
        np.arange(8.0),
        segment,
        training,
        100,
        visible=np.array([False]),
        config=MixtureConfig(),
    )
    assert result["unassigned_posterior"] == 1.0
    assert result["candidate_posterior"][0] == 0.0


def test_predictive_mixture_retains_underflowed_training_component() -> None:
    segment = np.zeros(8, dtype=int)
    training = np.array([True, True, True, True, False, False, False, False])
    # The candidate is crushed on training but exact on held-out.  Its displayed
    # posterior underflows to zero; its log weight must remain in prediction.
    candidate = np.array([[0.0, 300_000.0, -300_000.0, 300_000.0, 0.0, 0.0, 0.0, 0.0]])
    unassigned = np.array([0.0, 1.0, -1.0, 2.0, 1e9, -1e9, 1e9, -1e9])
    result = mixture_statistics(candidate, unassigned, segment, training, 10_000)
    assert result["candidate_posterior"][0] == 0.0
    assert np.isfinite(result["heldout_log_predictive"])
    # A probability-space implementation returns only the terrible unassigned
    # term here, hundreds of thousands of nats below the retained component.
    assert result["heldout_log_predictive"] > -10_000
