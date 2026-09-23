import importlib.util
from pathlib import Path

import numpy as np
import pytest

PATH = Path(__file__).parents[2] / "tools/research/ablate_soft_receiver_pairs.py"
SPEC = importlib.util.spec_from_file_location("ablate_soft_receiver_pairs", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_component_evidence_matches_independent_identity_and_null_oracle():
    train = np.log(np.array([0.2, 0.4, 0.8]))
    heldout = np.log(np.array([0.7, 0.5, 0.3]))
    null_train, null_heldout = np.log(0.6), np.log(0.9)
    population, prior = 11, 0.35
    actual_train, actual_joint = MODULE.component_log_evidence(
        train, heldout, null_train, null_heldout, population, prior
    )
    expected_train = prior / population * np.sum(np.exp(train)) + (1 - prior) * np.exp(null_train)
    expected_joint = prior / population * np.sum(np.exp(train + heldout)) + (1 - prior) * np.exp(
        null_train + null_heldout
    )
    assert actual_train == pytest.approx(np.log(expected_train), abs=1e-14)
    assert actual_joint == pytest.approx(np.log(expected_joint), abs=1e-14)


def test_soft_state_marginal_matches_probability_space_oracle_and_limits():
    independent, shared = -9.2, -7.7
    for q in (0.5, 0.9, 0.99):
        expected = np.log((1 - q) * np.exp(independent) + q * np.exp(shared))
        assert MODULE.mixed_log_evidence(independent, shared, q) == pytest.approx(
            expected, abs=1e-14
        )


def test_predictive_difference_uses_one_joint_latent_state_not_mixed_conditionals():
    q = 0.5
    independent_train, shared_train = -10.0, -4.0
    independent_joint, shared_joint = -12.0, -9.0
    mixed_train = MODULE.mixed_log_evidence(independent_train, shared_train, q)
    mixed_joint = MODULE.mixed_log_evidence(independent_joint, shared_joint, q)
    predictive_delta = (mixed_joint - mixed_train) - (independent_joint - independent_train)
    probability_oracle = np.log(
        ((1 - q) * np.exp(independent_joint) + q * np.exp(shared_joint))
        / ((1 - q) * np.exp(independent_train) + q * np.exp(shared_train))
    ) - (independent_joint - independent_train)
    assert predictive_delta == pytest.approx(probability_oracle, abs=1e-14)


def test_shared_five_block_partition_excludes_anchors_and_never_splits_visit():
    left = {
        "tracklet_id": "left",
        "paired_visit_ids": [f"l{x}" for x in range(12)],
        "t_s": list(range(12)),
        "y_hz": list(range(12)),
    }
    right = {
        "tracklet_id": "right",
        "paired_visit_ids": [f"r{x}" for x in range(12)],
        "t_s": list(range(12)),
        "y_hz": list(range(12)),
    }
    visits = {**{f"l{x}": x for x in range(12)}, **{f"r{x}": x for x in range(12)}}
    partition = MODULE.shared_five_block_partition(left, right, {"l3", "l4"}, {"r4"}, visits)
    left_arc, left_visit = MODULE._arc(left, {"l3", "l4"}, partition, visits)
    right_arc, right_visit = MODULE._arc(right, {"r4"}, partition, visits)
    for visit in set(left_visit).intersection(right_visit):
        assert np.unique(left_arc.training[left_visit == visit]).tolist() == [partition[visit]]
        assert np.unique(right_arc.training[right_visit == visit]).tolist() == [partition[visit]]
    assert 3 not in left_visit and 3 in right_visit
    assert sum(partition.values()) >= 2
    assert sum(not value for value in partition.values()) >= 2


def test_full_population_denominator_changes_signal_but_not_null_term():
    train = np.log(np.array([0.5, 0.25]))
    heldout = np.zeros(2)
    small = MODULE.component_log_evidence(train, heldout, -2.0, -1.0, 2, 0.5)[0]
    large = MODULE.component_log_evidence(train, heldout, -2.0, -1.0, 20, 0.5)[0]
    assert large < small
    null_only_expected = np.log(0.5) - 2.0
    assert large > null_only_expected
