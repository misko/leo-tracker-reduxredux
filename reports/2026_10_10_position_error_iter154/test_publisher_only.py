"""Pure presentation fixtures; no numerical model or recording access."""
import copy
import pytest
from publish import markdown, publish


def fixture():
    policies = {}
    for discovery in ('native', 'zero'):
        rows = []
        for index in range(12):
            arms = {}
            for arm in ('fitted-c', 'zero-c'):
                arms[arm] = dict(delta_km=-.2, **{
                    key: dict(status='selected', qualified=True,
                              error_km=error, frequency=dict(posterior_rms_hz=10))
                    for key, error in [('native', 1.), ('fixed', .8)]})
            rows.append(dict(label=f'member-{index}', arms=arms,
                             statuses=dict(native='complete', fixed='complete'),
                             phase_elapsed_s=dict(native=1., fixed=2.),
                             failure_reasons=dict(native=None, fixed=None),
                             regions=dict(native=[], fixed=[])))
        policies[discovery] = dict(rows=rows, progression=dict(passed=True),
                                  aggregates={}, historical_control_parity={})
    return dict(all48_terminal=True, progression_passed=True, policies=policies)


def test_condition_labels_and_frequency_separation(tmp_path):
    summary = fixture()
    before = copy.deepcopy(summary)
    publish(summary, tmp_path, render=lambda *args:None)
    body = (tmp_path/'RESULTS.md').read_text()
    assert 'Fitted-c discovery' in body and 'Zero-c discovery' in body
    assert 'Own-arm repair' in body and 'Control' in body
    assert 'Frequency fit is separate from position accuracy' in body
    assert summary == before


def test_missing_endpoint_and_unknown_time_are_explicit():
    summary = fixture()
    row = summary['policies']['zero']['rows'][0]
    row['statuses']['fixed'] = 'budget-exhausted'
    row['phase_elapsed_s']['fixed'] = None
    row['failure_reasons']['fixed'] = 'time | limit'
    for value in row['arms'].values():
        value['fixed'] = dict(status='no-selected-endpoint')
        value.pop('delta_km')
    body = markdown(summary)
    assert '| budget-exhausted | 0/2 | unavailable |' in body
    assert 'time &#124; limit' in body
    assert '| zero-c | unavailable | 10.000000 | unavailable |' in body


def test_unsealed_or_missing_policy_never_renders(tmp_path):
    summary = fixture()
    summary['all48_terminal'] = False
    with pytest.raises(ValueError):
        publish(summary, tmp_path, render=lambda *args:pytest.fail('early render'))
    summary['all48_terminal'] = True
    del summary['policies']['zero']
    with pytest.raises(ValueError):
        publish(summary, tmp_path, render=lambda *args:pytest.fail('early render'))
