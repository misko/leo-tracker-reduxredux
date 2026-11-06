import numpy as np
import pytest
from benchmark_algo07v3_training_kernel import trial
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_posterior_buffers import candidate_function, capture, reference

from leo.analysis.localization_v3 import event_position, history_position
from tests.tools.test_probe_algo07v3_annotation_arms import context


@pytest.mark.parametrize('arm', ['c0', 'fitted_c'])
def test_full_training_history_state_and_likelihood_exact(arm):
    d = context()
    before = trial(d, d['keep'], arm, reference.hierarchical_bound)
    d = context()
    operation, _, _ = candidate_function('buffers')
    after = trial(d, d['keep'], arm, operation)
    assert before['signature'] == after['signature']


@pytest.mark.parametrize('arm', ['c0', 'fitted_c'])
def test_capture_restores_aliases_and_preserves_training_mask(arm):
    d = context()
    before = fingerprint(d['keep'])
    aliases = [m.hierarchical_bound for m in (event_position, history_position)]
    args, kwargs = capture(d, d['keep'], arm)
    assert len(args) == 4 and args[1].shape[0] == len(args[0])
    result = reference.hierarchical_bound(*args, **kwargs)
    assert np.isfinite(result['negative_twice_elbo'])
    assert before == fingerprint(d['keep'])
    assert aliases == [m.hierarchical_bound for m in (event_position, history_position)]
