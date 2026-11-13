import json
from copy import deepcopy
from types import SimpleNamespace

import initial_discovery_probe as probe
import numpy as np
import pytest


def initial():
    state = dict(beta=np.zeros(8), phases=np.array([20., -20.]),
                 smooth=np.zeros((2, 1)), extra={})
    rows = [dict(component='curve', candidate_index=0, candidate_norad=10,
                 points=40, rms_hz=50., bias_hz=2., compatible=True)]
    arms = {arm: dict(fit=dict(parameters=np.array([1., 2.]), score=5.),
                      state=deepcopy(state), reference=np.zeros(1),
                      all_graph_associations=dict(tracks=[dict(
                          component='owned', norad=10, compatible=True)]))
            for arm in ('c0', 'fitted_c')}
    return dict(status='complete', selected_hypothesis=0, choices=[dict(
        hypothesis=0, node=dict(seed=dict(state=state, rows=rows), aliases=[0]), arms=arms)])


def evidence():
    return dict(audit=dict(initial=initial(), recovery_inventory=dict(selected_targets=[
        dict(track_id='new', component='curve'), dict(track_id='old', component='owned')]),
        predictive_recovery=dict(attempts=[
            dict(track_id='new', annotation=dict(norad=20), status='RF_qualified'),
            dict(track_id='old', annotation=dict(norad=10), status='RF_qualified')])))


def test_miss_census_distinguishes_missing_family_from_already_owned_target():
    missing, owned = probe.miss_census(evidence())
    assert missing == dict(track_id='new', component='curve', recovery_status='RF_qualified',
                           proposed_norad=20, present_in_initial_labels=False,
                           initial_accepted_owners=dict(c0=None, fitted_c=None))
    assert owned['present_in_initial_labels'] is True
    assert owned['initial_accepted_owners'] == dict(c0=10, fitted_c=10)


def test_proposal_reuses_corrected_c0_at_endpoint_without_mutating_or_accepting(monkeypatch):
    saved = initial()
    before = probe.fingerprint(saved)
    calls = []

    def explore(scan, state, point, method, **options):
        calls.append((state, point, method, options))
        np.testing.assert_array_equal(state['phases'], [15., -15.])
        state['beta'][0] = 123.
        row = dict(saved['choices'][0]['node']['seed']['rows'][0],
                   candidate_index=1, candidate_norad=20)
        return dict(state=state, rows=[row]), dict(candidate_hypotheses=2)

    monkeypatch.setattr(probe, 'explore', explore)
    monkeypatch.setattr(probe, 'AnchoredFamilies', lambda *args: SimpleNamespace(alias=[1]))
    result = probe.propose(None, saved)
    assert len(calls) == 1
    np.testing.assert_array_equal(calls[0][1], [1., 2.])
    assert calls[0][2:] == ('receiver_smooth', dict(compact_update=False))
    assert result['added_norads'] == [20]
    assert result['removed_norads'] == [10]
    assert result['changes'] == [dict(component='curve', previous_norad=10,
                                    proposed_norad=20, previous_alias=0, proposed_alias=1)]
    assert result['initial_evidence_unchanged'] is True
    assert result['position_inclusion_authorized'] is False
    assert result['position_fit_performed'] is False
    assert result['predictive_qualification_performed'] is False
    assert probe.fingerprint(saved) == before


def test_replay_checks_saved_objective_and_state_at_original_reference(monkeypatch):
    saved = initial()
    seen = []

    class Problem:
        def __init__(self, scan, node, sigma, fitted_c, *, reference):
            seen.append((node, fitted_c, reference))

        def residual(self, point):
            np.testing.assert_array_equal(point, [1., 2.])
            return np.array([1., 2.])

        def state(self, point):
            return deepcopy(saved['choices'][0]['arms']['c0']['state'])

    monkeypatch.setattr(probe, 'NormalPosition', Problem)
    result = probe.replay_initial(SimpleNamespace(radio_sigma_hz=150.), saved)
    assert result['score_difference'] == 0.
    assert result['genuine_previous'] is False
    assert seen[0][0] is saved['choices'][0]['node']
    assert seen[0][1] is False
    np.testing.assert_array_equal(seen[0][2], np.zeros(1))
    saved['choices'][0]['arms']['c0']['fit']['score'] = 6.
    with pytest.raises(ValueError, match='score replay mismatch'):
        probe.replay_initial(SimpleNamespace(radio_sigma_hz=150.), saved)


@pytest.mark.parametrize('kind', ['duplicate', 'incomplete'])
def test_ambiguous_or_incomplete_incumbent_rejected(kind):
    saved = initial()
    if kind == 'duplicate':
        saved['choices'].append(deepcopy(saved['choices'][0]))
    else:
        saved['status'] = 'unfinished'
    with pytest.raises(ValueError, match='completed selected'):
        probe.selected_branch(saved)


def test_plan_only_never_loads_archive_or_generates_proposal(tmp_path, monkeypatch):
    request = tmp_path / 'request.json'
    request.write_text('{}\n')
    monkeypatch.setattr(probe, 'request_inputs', lambda path: (
        {}, dict(identity=dict(run_id='run')), None))
    monkeypatch.setattr(probe, 'source_bindings', lambda: {})
    monkeypatch.setattr(probe, 'load_saved', lambda *args: pytest.fail('Archive loaded'))
    monkeypatch.setattr(probe, 'propose', lambda *args: pytest.fail('Proposal generated'))
    output = tmp_path / 'probe'
    assert probe.main(['--request', str(request), '--output', str(output),
                       '--focus-norad', '20']) == 0
    plan = json.loads((output / 'plan.json').read_text())
    assert plan['genuine_previous'] is False
    assert plan['focus_used_only_after_proposal'] is True
    assert plan['GPS_used'] is False
    assert plan['position_inclusion_authorized'] is False
    assert not (output / 'result.json').exists()


def test_existing_output_cannot_be_overwritten(tmp_path):
    with pytest.raises(SystemExit):
        probe.main(['--request', str(tmp_path / 'missing'), '--output', str(tmp_path),
                    '--focus-norad', '20'])
