import json

import census_algo07v5_training_recipes as census
import numpy as np
import pytest

from leo.contracts.digests import canonical_digest


def evidence():
    tracks = [dict(key=key, times=np.arange(n, dtype=float) + offset,
                   values=np.arange(n, dtype=float),
                   observation_ids=[f'{key}{i}' for i in range(n)])
              for key, n, offset in [('A', 3, 100), ('B', 3, 200),
                                     ('T', 12, 0), ('U', 12, 20)]]
    node = dict(seed=dict(rows=[dict(component='B', active_curvature=True, candidate_index=1),
                               dict(component='T', active_curvature=False, candidate_index=2),
                               dict(component='A', active_curvature=True, candidate_index=0)]),
                aliases=np.array([1, 2]))
    selected = [dict(track_id=key, track_index=i, inactive_fragment=False)
                for i, key in [(2, 'T'), (3, 'U')]]
    inventory = dict(tracks=[dict(t, current_large=True) for t in selected],
                     policy={a: dict(proposed_associated_ids=[]) for a in census.ARMS})
    cavity = dict(status='complete', accepted=False, selected=None,
                  baseline_node=node, baseline_entries=[], baseline_means=np.zeros(2),
                  model=dict(multiplier=1., nu=4., shrinkage=.5),
                  original_mask=np.array([True, False, True, False, True, True]),
                  powers=np.array([.3, .5]))
    return dict(preparation=dict(tracks=dict(tracks=tracks), sky=dict(test=np.array([1.]))),
                provenance=dict(runtime=dict(python='fake'), backend='fake'),
                audit=dict(cavity_policy=cavity,
                           recovery_inventory=dict(inventory=inventory, selected_targets=selected)))


def splits(monkeypatch, *, insufficient=False, target_dependent=False):
    seen = []

    def schedule(times, focus, **kwargs):
        seen.append((times.copy(), focus.copy(), kwargs))
        return [7, 8, 9], dict(geometry_only_early_exit=False)

    def split(times, focus, seed, plan):
        calibration = np.array([True, True, False, True, False, True])
        if target_dependent and focus[0] > 10:
            calibration[0] = False
        training = np.arange(len(focus)) < (7 if insufficient else 8)
        train = np.r_[calibration, training]
        return train, ~train, dict(seed=seed)

    monkeypatch.setattr(census, 'partition_schedule', schedule)
    monkeypatch.setattr(census, 'planned_split', split)
    return seen


def test_member_order_full_keep_slice_and_duplicate_targets(monkeypatch):
    seen = splits(monkeypatch)
    report = census.census_evidence(evidence())
    np.testing.assert_array_equal(seen[0][0][:6], [200, 201, 202, 100, 101, 102])
    assert seen[0][2] == dict(shifted_origin=True)
    assert report['member_indices'] == [1, 0]
    expected = np.array([True, False, False, False, False, True])
    assert {r['keep_sha256'] for r in report['recipes']} == {census.fingerprint(expected)}
    assert report['counts']['potential_calls'] == 12
    assert report['counts']['distinct_recipes'] == 2
    assert report['counts']['potential_redundant_calls'] == 10
    assert report['counts']['executed_proven_hits'] is None
    assert report['recipes'][0]['recipe_sha256'] == report['recipes'][6]['recipe_sha256']


def test_identical_seed_does_not_imply_same_calibration_mask(monkeypatch):
    splits(monkeypatch, target_dependent=True)
    report = census.census_evidence(evidence())
    assert report['counts']['distinct_recipes'] == 4
    assert report['recipes'][0]['seed'] == report['recipes'][6]['seed']
    assert report['recipes'][0]['recipe_sha256'] != report['recipes'][6]['recipe_sha256']


def test_changed_arm_mask_or_context_changes_recipe():
    key = census.recipe_key('context', 'c0', [True, False])
    assert key != census.recipe_key('context', 'fitted_c', [True, False])
    assert key != census.recipe_key('context', 'c0', [False, True])
    assert key != census.recipe_key('another', 'c0', [True, False])


@pytest.mark.parametrize('field', ['preparation', 'node', 'model', 'means', 'powers', 'provenance'])
def test_saved_context_changes_prevent_recipe_equality(monkeypatch, field):
    splits(monkeypatch)
    first, other = evidence(), evidence()
    cavity = other['audit']['cavity_policy']
    if field == 'preparation':
        other['preparation']['sky']['test'][0] = 2
    elif field == 'node':
        cavity['baseline_node']['aliases'][0] += 1
    elif field == 'model':
        cavity['model']['multiplier'] = 2.
    elif field == 'means':
        cavity['baseline_means'][0] = 1.
    elif field == 'powers':
        cavity['powers'] = np.ones(3)
    else:
        other['provenance']['backend'] = 'different'
    assert census.census_evidence(first)['recipes'][0]['recipe_sha256'] != (
        census.census_evidence(other)['recipes'][0]['recipe_sha256'])


def test_unit_powers_ignore_original_weight_values(monkeypatch):
    splits(monkeypatch)
    first, other = evidence(), evidence()
    other['audit']['cavity_policy']['powers'][:] = 9.
    assert census.census_evidence(first)['recipes'] == census.census_evidence(other)['recipes']


def test_accepted_cavity_uses_chosen_node_entries_and_means(monkeypatch):
    splits(monkeypatch)
    value = evidence()
    cavity = value['audit']['cavity_policy']
    cavity.update(accepted=True, selected=dict(node=cavity.pop('baseline_node'),
                                              entries=cavity.pop('baseline_entries'),
                                              means=cavity.pop('baseline_means')))
    report = census.census_evidence(value)
    assert report['member_indices'] == [1, 0]
    assert report['counts']['potential_calls'] == 12


def test_inactive_fragment_uses_both_arm_curved_and_entry_occupied_ids(monkeypatch):
    seen = splits(monkeypatch)
    value = evidence()
    inv = value['audit']['recovery_inventory']
    target = inv['selected_targets'][0]
    target['inactive_fragment'] = True
    inv['selected_targets'] = [target]
    inventory = inv['inventory']
    inventory['policy']['c0']['proposed_associated_ids'] = ['T0']
    inventory['policy']['fitted_c']['proposed_associated_ids'] = ['T1']
    value['audit']['cavity_policy']['baseline_entries'] = [dict(observation_ids=['T2'])]
    value['preparation']['tracks']['tracks'][1]['observation_ids'][0] = 'T3'
    inventory['tracks'][0]['observation_ids'] = ['T11']
    report = census.census_evidence(value)
    assert report['targets'][0]['fragment_observation_ids'] == [f'T{i}' for i in range(4, 12)]
    np.testing.assert_array_equal(seen[0][1], np.arange(4., 12.))
    assert report['targets'][0]['context_sha256'] != report['original_context_sha256']


def test_inactive_contexts_separate_but_mask_only_upper_bound_combines(monkeypatch):
    splits(monkeypatch)
    value = evidence()
    for index in (2, 3):
        track = value['preparation']['tracks']['tracks'][index]
        track['times'] = np.r_[track['times'], track['times'][-1] + 1]
        track['values'] = np.r_[track['values'], 12.]
        track['observation_ids'].append(track['key'] + '12')
    inventory = value['audit']['recovery_inventory']['inventory']
    for arm in census.ARMS:
        inventory['policy'][arm]['proposed_associated_ids'] = ['T0', 'U0']
    for target in value['audit']['recovery_inventory']['selected_targets']:
        target['inactive_fragment'] = True
    report = census.census_evidence(value)
    assert report['counts']['distinct_recipes'] == 4
    assert report['counts']['calibration_mask_only_distinct'] == 2
    assert report['counts']['calibration_mask_only_redundant_upper_bound'] == 10


def test_insufficient_folds_do_not_count_training_calls(monkeypatch):
    splits(monkeypatch, insufficient=True)
    report = census.census_evidence(evidence())
    assert report['counts']['potential_calls'] == 0
    assert all(f['status'] == 'insufficient_group_support'
               for t in report['targets'] for f in t['folds'])


def test_geometry_only_early_exit_has_no_potential_calls(monkeypatch):
    monkeypatch.setattr(census, 'partition_schedule',
                        lambda *args, **kwargs: ([], dict(geometry_only_early_exit=True)))
    report = census.census_evidence(evidence())
    assert report['counts']['potential_calls'] == 0
    assert all(t['geometry_only_early_exit'] for t in report['targets'])


def test_original_mask_length_and_active_target_are_rejected():
    value = evidence()
    value['audit']['cavity_policy']['original_mask'] = np.ones(1, bool)
    with pytest.raises(ValueError, match='Original mask'):
        census.census_evidence(value)
    value = evidence()
    target = value['audit']['recovery_inventory']['selected_targets'][0]
    target['track_index'] = 1
    value['audit']['recovery_inventory']['inventory']['tracks'][0]['track_index'] = 1
    with pytest.raises(ValueError, match='active calibration'):
        census.census_evidence(value)


def test_real_timestamp_schedule_without_context_or_likelihood():
    value = evidence()
    tracks = value['preparation']['tracks']['tracks']
    for index in (2, 3):
        tracks[index].update(times=np.arange(120.), values=np.arange(120.),
                             observation_ids=[f'{index}-{j}' for j in range(120)])
    report = census.census_evidence(value)
    assert report['counts']['potential_calls'] == 12
    assert all(len(t['planned_seeds']) == 3 for t in report['targets'])


def saved_request(tmp_path, monkeypatch, wrapped):
    identity = dict(run_id='run', session_id='session', input_sha256='sha256:input')
    job = dict(output_root=str(tmp_path), identity=identity, runtime=dict(python='fake'))
    request = dict(job=job, algorithm='algo07v4-native-v1') if wrapped else job
    path = tmp_path / 'request.json'
    path.write_text(json.dumps(request))
    value = evidence()
    value.update(identity=identity, provenance=dict(request_sha256=canonical_digest(request),
                                                   configuration=dict(request=job)))
    receipt = dict(result_sha256='sha256:archive', result_bytes=123, **identity)
    saved = dict(evidence=value, receipt=receipt, sha256=canonical_digest(receipt))
    calls = []

    class Store:
        def __init__(self, root):
            assert root == tmp_path

        def load(self, run_id):
            calls.append(run_id)
            return saved

    monkeypatch.setattr(census, 'LocalizationV4Store' if wrapped else 'LocalizationV3Store', Store)
    return path, saved, calls


@pytest.mark.parametrize('wrapped', [False, True])
def test_cli_public_store_binding_and_outputs(tmp_path, monkeypatch, wrapped, capsys):
    splits(monkeypatch)
    path, saved, calls = saved_request(tmp_path, monkeypatch, wrapped)
    out = tmp_path / 'out'
    assert census.main(['--request', str(path), '--request', str(path), '--output', str(out)]) == 0
    report = json.loads((out / 'census.json').read_text())
    assert calls == ['run']
    assert report['statuses'] == dict(complete=1, missing=0, mismatching=0)
    assert report['counts']['potential_calls'] == 12
    assert report['cache_implemented'] is False
    assert report['inference_rerun'] is False
    assert report['requests'][0]['receipt_sha256'] == saved['sha256']
    assert report['requests'][0]['archive_sha256'] == 'sha256:archive'
    assert report['requests'][0]['archive_bytes'] == 123
    assert len(report['input_bindings']) == 3
    assert json.loads(capsys.readouterr().out)['counts'] == report['counts']


@pytest.mark.parametrize('bad', ['digest', 'job', 'identity', 'receipt', 'receipt_digest'])
def test_request_binding_mismatch_is_nonzero(tmp_path, monkeypatch, bad):
    path, saved, _ = saved_request(tmp_path, monkeypatch, False)
    if bad == 'digest':
        saved['evidence']['provenance']['request_sha256'] = 'wrong'
    elif bad == 'job':
        saved['evidence']['provenance']['configuration']['request'] = {}
    elif bad == 'identity':
        saved['evidence']['identity'] = {}
    elif bad == 'receipt':
        saved['receipt']['run_id'] = 'wrong'
    else:
        saved['sha256'] = 'wrong'
    assert census.main(['--request', str(path), '--output', str(tmp_path / 'out')]) == 1
    report = json.loads((tmp_path / 'out' / 'census.json').read_text())
    assert report['statuses']['mismatching'] == 1


def test_missing_request_is_reported_and_nonzero(tmp_path):
    out = tmp_path / 'out'
    assert census.main(['--request', str(tmp_path / 'absent'), '--output', str(out)]) == 1
    report = json.loads((out / 'census.json').read_text())
    assert report['statuses']['missing'] == 1
    assert report['counts']['potential_calls'] == 0


def test_pilot_ledger_loads_eight_baselines(tmp_path, monkeypatch):
    rows = []
    for i in range(8):
        folder = tmp_path / str(i)
        folder.mkdir()
        (folder / 'request.json').write_text('{}')
        rows.append(dict(case=str(i), config='baseline', output=str(folder)))
    ledger = tmp_path / 'ledger.json'
    ledger.write_text(json.dumps(dict(runs=rows + [dict(config='cheap64')])))
    seen = []

    def read(path):
        seen.append(path)
        return dict(status='complete', recipes=[])

    monkeypatch.setattr(census, 'census_request', read)
    assert census.main(['--pilot-ledger', str(ledger), '--output', str(tmp_path / 'out')]) == 0
    assert seen == [tmp_path / str(i) / 'request.json' for i in range(8)]


def test_output_qnap_and_invalid_ledger_are_rejected(tmp_path):
    with pytest.raises(SystemExit):
        census.main(['--request', 'anything', '--output', '/mnt/qnap01/forbidden'])
    ledger = tmp_path / 'ledger.json'
    ledger.write_text(json.dumps(dict(runs=[])))
    with pytest.raises(SystemExit):
        census.main(['--pilot-ledger', str(ledger), '--output', str(tmp_path / 'out')])
