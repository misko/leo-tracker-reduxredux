import benchmark_algo07v3_training_kernel as probe
import pytest

from tests.tools.test_probe_algo07v3_annotation_arms import context


@pytest.mark.parametrize('arm', ['c0', 'fitted_c'])
def test_complete_training_history_calculation_and_state_match(arm):
    d = context()
    before = probe.trial(d, d['keep'], arm, probe.reference_kernel.hierarchical_bound)
    d = context()
    candidate, _, _ = probe.candidate_function()
    after = probe.trial(d, d['keep'], arm, candidate)
    assert before['signature'] == after['signature']


def test_failed_training_restores_both_runtime_aliases():
    original = [m.hierarchical_bound for m in (probe.history_position, probe.event_position)]
    candidate, _, _ = probe.candidate_function()
    with pytest.raises(RuntimeError), probe.kernel(candidate):
        assert all(m.hierarchical_bound is candidate
                   for m in (probe.history_position, probe.event_position))
        raise RuntimeError('abort')
    assert original == [m.hierarchical_bound
                        for m in (probe.history_position, probe.event_position)]
