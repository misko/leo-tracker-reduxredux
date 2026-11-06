import pytest
from probe_algo07v3_native_recovery_queue import fork_trials, recovery_trial, signature


def prepared():
    return dict(recovery_context=dict(node={}, keep=[True]), inventory={'tracks': []})


def operation(context, evidence, *, run_stage, on_selection, **kwargs):
    _, value = run_stage('first', lambda: dict(arms={'c0': 1., 'fitted_c': 2.}))
    on_selection(value)
    return dict(decision='selected', value=value)


def test_complete_stage_and_selection_are_fingerprinted():
    row = recovery_trial(prepared(), operation)
    assert row['stage_signatures'] == {'first': signature({'arms': {'c0': 1., 'fitted_c': 2.}})}
    assert row['decision'] == 'selected'
    assert row['seconds'] >= 0 and row['cpu_seconds'] >= 0


def test_fork_trials_preserve_same_parent_checkpoint_and_both_arms():
    data = prepared()
    rows = []
    assert len(fork_trials(data, {'a': (operation, None)}, ['a', 'a'], rows.append)) == 2
    assert data == prepared()
    assert all(row['exact'] for row in rows)


def test_stage_difference_fails_even_when_final_decision_matches():
    def changed(context, evidence, *, run_stage, on_selection, **kwargs):
        run_stage('extra', lambda: 3)
        return operation(context, evidence, run_stage=run_stage, on_selection=on_selection)
    rows = []
    with pytest.raises(ValueError, match='checkpoint changed'):
        fork_trials(prepared(), {'a': (operation, None), 'b': (changed, None)},
                    ['a', 'b'], rows.append)
    assert not rows[-1]['exact']


def test_failed_scientific_result_and_mutation_cannot_pass():
    def failed(*args, **kwargs):
        return dict(failure='bad inputs')
    with pytest.raises(ValueError, match='Recovery failed'):
        recovery_trial(prepared(), failed)

    def mutated(context, evidence, **kwargs):
        context['keep'].append(False)
        return dict(decision='selected')
    with pytest.raises(ValueError, match='inputs changed'):
        recovery_trial(prepared(), mutated)


def test_stateful_replay_refused():
    data = prepared()
    data['recovery_context']['numerical_policy'] = {}
    with pytest.raises(ValueError, match='Stateful'):
        recovery_trial(data, operation)
