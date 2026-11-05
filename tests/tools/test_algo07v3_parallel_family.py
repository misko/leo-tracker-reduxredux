"""Family c-arm isolation preserves paired rejection and numerical records."""

import copy

import algo07v3_prefamily_policy_oracle as history_policy
import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_parallel_family import transformed_functions

from leo.operations.localization_v3_parallel import ParallelFitFailure, map_initial_arms
from tests.analysis.test_localization_v3_position import prepared


@pytest.mark.parametrize("masked", [False, True])
def test_real_curved_pair_retains_every_output_bit(masked):
    scan, node = prepared()
    scan.previous_sources = {}
    scan.elements = {'99999': dict(provenance=dict(element_epoch_utc_ns=0))}
    keep = np.ones(41, bool)
    if masked:
        keep[::3] = False
    arguments = (scan, node, keep, np.ones(1), np.zeros(1), dict(multiplier=1., nu=4.))
    before = keep.copy()
    namespace, _, _ = transformed_functions(map_initial_arms)
    reference = history_policy.history_fit(*copy.deepcopy(arguments))
    candidate = namespace["history_fit"](*copy.deepcopy(arguments))
    assert fingerprint(reference) == fingerprint(candidate)
    np.testing.assert_array_equal(keep, before)


def test_failed_child_cannot_become_a_rejected_pair(monkeypatch):
    scan, node = prepared()
    scan.previous_sources = {}
    scan.elements = {'99999': dict(provenance=dict(element_epoch_utc_ns=0))}

    def broken(*args):
        if args[3] == "fitted_c":
            raise RuntimeError("deliberate child failure")
        return dict(gates=dict(tracks=[]))

    monkeypatch.setattr(history_policy, "refit", broken)
    namespace, _, _ = transformed_functions(map_initial_arms)
    with pytest.raises(ParallelFitFailure, match="deliberate child failure"):
        namespace["history_fit"](scan, node, np.ones(41, bool), np.ones(1), np.zeros(1),
                                 dict(multiplier=1., nu=4.))
