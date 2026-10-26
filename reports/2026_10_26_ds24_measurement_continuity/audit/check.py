"""Independent small algebra and saved-artifact audits; no scientific reruns."""
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import subprocess
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(name, value):
    with (ROOT / 'audit' / name).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def bindings(files):
    bad = [path for path, expected in files.items() if sha(path) != expected]
    assert not bad, bad
    return len(files)


def log_normal(raw, covariance):
    root = np.linalg.cholesky(covariance)
    white = np.linalg.solve(root, raw)
    return -.5 * (float(white @ white) + 2*np.log(np.diag(root)).sum()
        + len(raw)*np.log(2*np.pi))


def logsumexp(values):
    values = np.asarray(values)
    maximum = float(np.max(values))
    return maximum + float(np.log(np.exp(values-maximum).sum()))


def conditional_oracle(y, covariance, means, modes, log_prior, train, held, period, aliases):
    """Dense whole-observation oracle; each node/alias has one joint measure."""
    records = []
    for node, prior in enumerate(log_prior):
        S = covariance + modes[node] @ modes[node].T
        TT = S[np.ix_(train, train)]
        HT = S[np.ix_(held, train)]
        HH = S[np.ix_(held, held)]
        conditional_covariance = HH - HT @ np.linalg.solve(TT, HT.T)
        for alias in aliases:
            prior_alias = float(prior - np.log(len(aliases)))
            mean = means[node] - alias*period
            raw = y-mean
            train_score = log_normal(raw[train], TT)
            update = HT @ np.linalg.solve(TT, raw[train])
            joint_score = log_normal(raw, S)
            conditional_score = log_normal(raw[held]-update, conditional_covariance)
            records.append(dict(log_weight=prior_alias+train_score,
                log_joint=prior_alias+joint_score,
                log_conditional=conditional_score,
                mean=mean[held]+update, covariance=conditional_covariance))
    train_density = logsumexp([row['log_weight'] for row in records])
    weights = np.exp(np.array([row['log_weight'] for row in records])-train_density)
    mean = sum(weight*row['mean'] for weight, row in zip(weights, records, strict=True))
    covariance_out = sum(weight*(row['covariance'] + np.outer(row['mean']-mean, row['mean']-mean))
        for weight, row in zip(weights, records, strict=True))
    direct = logsumexp([row['log_joint'] for row in records])-train_density
    conditional = logsumexp([row['log_weight']+row['log_conditional'] for row in records])-train_density
    return dict(log_density=direct, conditional_log_density=conditional,
        mean=mean, covariance=covariance_out, weights=weights,
        train_log_density=train_density)


def attribution():
    began = time.monotonic()
    here = ROOT / 'attribution'
    summary = read(here / 'summary.json')
    original = Path(summary['source'])
    assert sha(original) == summary['source_sha256']
    with (here / 'stage_attribution.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    raw = read(original)
    winners = {(slot['scenario'], slot['seed'], receiver['receiver_id']):
        receiver['summary']['highest_margin_accepted']
        for slot in raw['slots'] for receiver in slot['receivers'] if slot['sources']}
    assert len(rows) == len(winners) == 28
    for row in rows:
        key = row['scenario'], int(row['seed']), int(row['receiver_id'])
        winner = winners[key]
        assert int(row['candidate_rank']) == winner['candidate_rank']
        final = float(row['final_CFO_hz'])
        assert final == winner['fractional_tracking_cfo_hz']
        assert float(row['acquired_CFO_hz']) == winner['acquired_cfo_hz']
        assert float(row['fractional_GLRT_residual_hz']) == winner['fractional_residual_cfo_hz']
        assert abs(final-float(row['acquired_CFO_hz'])-float(row['fractional_GLRT_residual_hz'])) < 1e-8
        assert abs(float(row['final_minus_reference_hz']) - float(row['acquired_minus_reference_hz'])
            - float(row['fractional_GLRT_residual_hz'])) < 1e-8
    assert summary['scorer_symbols'] == list(range(2, 66))
    assert summary['FFT_grid_size'] == 512
    assert abs(summary['grid_spacing_hz'] - (1/4.4e-6)/512) < 1e-9
    assert summary['new_detector_calls'] == summary['new_synthetic_inputs'] == 0
    save('attribution.json', dict(all_passed=True, rows=28,
        source_sha256=sha(original), summary_sha256=sha(here / 'summary.json'),
        decomposition_and_actual_candidate_identity_verified=True,
        new_detector_calls=0, audit_seconds=time.monotonic()-began,
        scope='Saved numerical stage decomposition, not proof why a bin wins or of physical bias.'))


def measurement_preflight():
    began = time.monotonic()
    here = ROOT / 'measurement'
    protocol = read(here / 'protocol.json')
    checked = bindings(protocol['files'])
    assert protocol['paired_detector_calls'] == 70 and protocol['detector_receivers_per_call'] == 2
    assert protocol['numerical_budget_seconds'] == 600 and protocol['max_workers'] == protocol['blas_threads'] == 1
    assert protocol['times_s'] == list(range(16)) and not protocol['operational_adoption']
    assert {(row['name'], row['law'], tuple(row['epochs'])) for row in protocol['sequences']} == {
        (name, law, epochs) for name, epochs in [('coincident', (127, 127)), ('separated', (127, 811))]
        for law in ('sampled_deployed', 'continuous')}
    prep = read(here / 'preparation.json')
    identity = read(here / 'detector_identity.json')
    assert prep['all_passed'] and prep['graph_port_assigned'] == 32 and prep['tests_run'] == 9
    assert not prep['detector_called'] and not prep['capture_attested']
    assert prep['seconds'] == protocol['preparation_seconds'] and prep['seconds'] < 600
    assert prep['prior_failed_identity_and_diagnostic_seconds'] > 0
    assert identity['code_digest'] == prep['code_digest'] == 'sha256:124afbbc81870a4079b272bd828d4a99f716e54624a073d9cb13acc2a1b7fe16'
    assert identity['environment_digest'] == prep['environment_digest'] == 'sha256:8ccb220369bccb42b7bea5dcd3bfa546e132d2250a674e6eac7388a2a425e3b9'
    assert bindings(identity['actual_imported_sources'])
    config = read(Path('/home/mouse9911/gits/leo-tracker-reduxredux') /
        'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json')['config']
    assert config == protocol['graph_config']
    assert config['noise_sigma_hz']*config['association_sigma'] == 450
    assert len(prep['boundary_mismatch_indices']) == 68
    assert all(index % 44 == 0 for index in prep['boundary_mismatch_indices'])
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(here),
        '-p', 'test_experiment.py'], env=env, text=True, capture_output=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert bindings(protocol['files']) == checked
    save('measurement_preflight.json', dict(all_passed=True,
        protocol_sha256=sha(here / 'protocol.json'), frozen_bindings_checked=checked,
        actual_graph_input_smoke_rows=32, detector_calls_by_audit=0,
        declared_detector_calls=70, known_template_boundary_mismatch_retained=True,
        production_selector_and_actual_graph_contract_reviewed=True,
        truth_used_only_for_separate_controls=True,
        test_stdout=result.stdout, test_stderr=result.stderr,
        audit_seconds=time.monotonic()-began,
        scope='Synthetic one-second cadence and pilot-only inverse-model/discretization controls; no physical waveform authority or field/localization calibration.'))


def measurement_terminal():
    began = time.monotonic()
    here = ROOT / 'measurement'
    protocol = read(here / 'protocol.json')
    seal = read(here / 'RF_seal.json')
    checked = bindings(protocol['files']) + bindings(seal['files'])
    assert seal['protocol_sha256'] == sha(here / 'protocol.json') and seal['all_selected_terminal']
    execution = read(here / 'execution.json')
    assert execution['slots'] == execution['complete'] == 70
    assert execution['cumulative_worker_seconds'] <= 600 and execution['detector_calls_not_retried']
    assert not any(execution[k] for k in ('original_IQ_read', 'new_RF', 'position_fit', 'truth_used_for_actual_selection'))
    identity = read(here / 'execution_detector.json')
    assert identity['identity_before'] == identity['identity_after'] == read(here / 'detector_identity.json')
    slots = [read(path) for path in sorted((here / 'slots').glob('*.json'))]
    assert len(slots) == 70 and all(slot['status'] == 'complete' for slot in slots)
    assert sum(len(slot['receivers']) for slot in slots) == 140
    assert all(slot['input']['clipping_samples'] == 0 for slot in slots)
    assert all(len(rx['candidates']) <= 8 for slot in slots for rx in slot['receivers'])
    for visit in range(16):
        matched = [slot for slot in slots if not slot['name'].startswith('closure_') and slot['visit'] == visit]
        assert len(matched) == 4 and len({s['input']['noise_sha256'] for s in matched}) == 1
    assert len({s['input']['noise_sha256'] for s in slots if s['name'].startswith('closure_')}) == 1
    def winner(candidates):
        eligible = [c for c in candidates if c['fractional_epoch_status'] == 'complete'
            and c['fractional_margin'] is not None and c['fractional_epoch_offset_samples'] is not None
            and c['fractional_tracking_cfo_hz'] is not None and c['fractional_margin'] >= .025]
        return max(eligible, key=lambda c:(c['fractional_margin'], -c['candidate_rank'])) if eligible else None
    period = protocol['graph_config']['alias_spacing_hz']
    summaries = []
    for sequence in execution['sequences']:
        name = sequence['name']
        assert sequence['status'] == 'complete'
        assert sha(sequence['graph_path']) == sequence['graph_sha256']
        graphs = read(sequence['graph_path'])
        own_slots = {slot['visit']:slot for slot in slots if slot['name'] == name}
        assert set(own_slots) == set(range(16))
        expected = {}
        for visit, slot in own_slots.items():
            for receiver in slot['receivers']:
                selected = winner(receiver['candidates'])
                if selected is None:
                    continue
                rx = int(receiver['receiver_id'])
                oid = 'sha256:'+hashlib.sha256(f'synthetic:{name}:RX{rx}:visit{visit}'.encode()).hexdigest()
                expected[oid] = slot, selected, rx
        for stage in ('actual', 'acquired_stage'):
            graph = graphs[stage]
            rows = {row['observation_id']:row for row in graph['rows']}
            assert set(rows) == set(expected) and len(rows) == len(graph['rows'])
            assert graph['synthetic_clock'] and not graph['qualified_capture']
            for oid, (slot, selected, rx) in expected.items():
                row = rows[oid]
                assert row['time_s'] == slot['time_s']+.01 and row['receiver'] == rx+1
                assert row['candidate_rank'] == selected['candidate_rank']
                assert row['fractional_margin'] == selected['fractional_margin']
                field = 'fractional_tracking_cfo_hz' if stage == 'actual' else 'acquired_cfo_hz'
                assert row['measured_cfo_hz'] == selected[field]
            assigned = [oid for track in graph['tracks'] for oid in track['observation_ids']]
            assert len(assigned) == len(set(assigned)) == graph['assigned']
            assert set(assigned) <= set(rows)
            assert set(graph['unresolved_ids']) == set(rows)-set(assigned)
            tracks = []
            for track in graph['tracks']:
                lane = [row for row in graph['rows'] if (row['receiver'],row['channel']) == (track['receiver'],track['channel'])]
                indices = track['indices']
                assert [lane[i]['observation_id'] for i in indices] == track['observation_ids']
                np.testing.assert_array_equal([lane[i]['time_s'] for i in indices], track['times'])
                lifts = (np.asarray(track['values']) - np.array([lane[i]['measured_cfo_hz'] for i in indices]))/period
                assert np.max(abs(lifts-np.rint(lifts))) < 1e-10
                labels = {'A':0, 'B':0, 'ambiguous':0, 'unmatched':0}
                for oid in track['observation_ids']:
                    slot, _, _ = expected[oid]
                    truth = [s['cfo0']+s['rate']*(slot['time_s']+.01) for s in slot['sources']]
                    distances = [abs((rows[oid]['measured_cfo_hz']-f+period/2)%period-period/2) for f in truth]
                    close = [i for i, delta in enumerate(distances) if delta <= 450]
                    label = ('A','B')[close[0]] if len(close) == 1 else ('ambiguous' if close else 'unmatched')
                    labels[label] += 1
                for piece in track['pieces']:
                    use = piece['indices']
                    t = np.array([lane[i]['time_s'] for i in use])
                    y = np.array([lane[i]['measured_cfo_hz'] for i in use])
                    fitted = np.polynomial.legendre.legval((t-piece['reference_time_s'])/piece['time_scale_s'],piece['coefficients_hz'])
                    residual = (y-fitted+period/2)%period-period/2
                    assert np.max(abs(residual)) < 450+1e-6
                tracks.append(dict(key=track['key'], points=len(track['observation_ids']),
                    quality_status=track['quality_status'], labels=labels,
                    contains_both_unique_truth_labels=bool(labels['A'] and labels['B'])))
            summaries.append(dict(sequence=name, stage=stage, selected_rows=len(rows),
                assigned=graph['assigned'], unresolved=len(graph['unresolved_ids']),tracks=tracks))
        for source, graph in read(here/'graphs'/f'{name}_oracle.json').items():
            assert source in ('A','B') and len(graph['rows']) == 32
            assert not set(expected) & {row['observation_id'] for row in graph['rows']}
    save('measurement_terminal.json', dict(all_passed=True,
        protocol_sha256=sha(here/'protocol.json'), RF_seal_sha256=sha(here/'RF_seal.json'),
        frozen_bindings_checked=checked, detector_slots=70, receiver_outputs=140,
        graphs_complete=4, actual_selection_source_independent=True,
        graph_input_ids_and_gates_verified=True, summaries=summaries,
        cumulative_scientific_worker_seconds=execution['cumulative_worker_seconds'],
        audit_seconds=time.monotonic()-began, detector_calls_by_audit=0, graph_reruns_by_audit=0,
        scope='Known synthetic trajectories and inverse-model closure; mixed descriptive labels are not physical-source or field-bias proof.'))


def recorded_readback():
    began = time.monotonic()
    here = ROOT / 'recorded'
    summary = read(here / 'summary.json')
    checked = bindings(summary['inputs_sha256'])
    checked += bindings({str(here/path):digest for path,digest in read(here/'seal.json').items()})
    def rows(name):
        with (here/name).open() as stream:
            return list(csv.DictReader(stream))
    winners, alternatives, owners = rows('winners.csv'), rows('alternatives.csv'), rows('owners.csv')
    assert len(winners) == summary['winning_points'] == 3754
    assert len(owners) == summary['original_owners'] == 117
    assert len(alternatives) == summary['nearby_alternative_records'] == 501
    obs_path = next(Path(p) for p in summary['inputs_sha256'] if p.endswith('/observations.json'))
    obs = {row['observation_id']:row for row in read(obs_path)}
    assert {row['observation_id'] for row in winners} == set(obs)
    flagged = set()
    counts = {}
    for row in alternatives:
        oid = row['observation_id']
        flagged.add(oid); counts[oid] = counts.get(oid,0)+1
        delta = float(row['alternative_CFO_hz'])-float(row['winner_CFO_hz'])
        assert abs(delta-float(row['raw_CFO_delta_hz'])) < 1e-8
        circular = (delta+(1/4.4e-6)/2)%(1/4.4e-6)-(1/4.4e-6)/2
        assert abs(circular-float(row['circular_CFO_delta_hz'])) < 1e-8
        assert 250 < abs(circular) <= 5000
        assert abs(float(row['circular_epoch_delta_samples'])) <= 3
        assert float(row['alternative_margin']) >= .025
    assert len(flagged) == summary['flagged_winners'] == 483
    for row in winners:
        oid = row['observation_id']; original = obs[oid]
        assert float(row['winner_CFO_hz']) == original['measured_cfo_hz']
        assert float(row['winner_margin']) == original['fractional_margin']
        assert float(row['time_s']) == original['time_s']
        assert (row['proximity_flag']=='True') == (oid in flagged)
        assert int(row['nearby_alternative_count']) == counts.get(oid,0)
    assert sum(int(row['flagged_points']) > 0 for row in owners) == summary['flagged_owner_count'] == 96
    target = next(row for row in owners if row['owner'] == summary['target']['owner'])
    assert int(target['original_points']) == 20 and int(target['flagged_points']) == 0
    save('recorded_readback.json', dict(all_passed=True,
        summary_sha256=sha(here/'summary.json'), source_files_checked=checked,
        winning_points=3754, proximity_flagged=483, owners_with_flags=96,
        original_owners=117, alternative_records=501, target_flags=0, target_points=20,
        audit_seconds=time.monotonic()-began, new_detector_calls=0, new_IQ_reads=0,
        scope='Thresholded exported-peak proximity, neither independent sources nor contamination evidence; no flag for the highlighted target.'))


def prediction_preflight02():
    began = time.monotonic()
    own = ROOT / 'prediction'; here = own / 'run02'
    protocol = read(here/'protocol.json')
    checked = bindings(protocol['bindings'])
    assert protocol['noise_training_excludes_whole_D'] and protocol['initial_preparation_preserved_unexecuted']
    assert protocol['slots'] == 8 and protocol['cap_worker_seconds'] == 300
    assert protocol['orders'] == [32,64] and protocol['primary_order'] == 64
    assert protocol['failed_noise_preparation_charged_upper_bound_seconds'] == 90
    prefix = protocol['preparation_seconds']+protocol['test_seconds']
    assert 90 < prefix < 300
    assert not (own/'execution_started.json').exists() and not (here/'execution_started.json').exists()
    prep = read(here/'preparation.json')
    assert prep['original_noise_samples'] == 3428 and prep['new_noise_samples'] == 3399
    assert prep['excluded_noise_samples'] == 29
    assert all(row['actual_point_noise_max_error'] == 0 and row['noise_samples'] == 3399 for row in prep['records'])
    assert len(prep['entire_pipeline_redactions']) == 8
    assert all(row['noise_model_exact'] and max(row['errors'].values()) <= 1e-8
        and row['actual_point_noise_max_error'] == 0 for row in prep['entire_pipeline_redactions'])
    split = read(own/'split.json')
    assert split['identity_selected_on_all_D']
    full_ids = split['complete_owner_IDs']
    assert len(full_ids) == len(set(full_ids)) == 29
    folds = split['folds']
    assert [len(folds[0]['train_IDs']),len(folds[0]['held_IDs'])] == [14,15]
    assert set(folds[0]['train_IDs']) | set(folds[0]['held_IDs']) == set(full_ids)
    assert not set(folds[0]['train_IDs']) & set(folds[0]['held_IDs'])
    assert folds[0]['train_IDs'] == folds[1]['held_IDs'] and folds[0]['held_IDs'] == folds[1]['train_IDs']
    spec = importlib.util.spec_from_file_location('audited_conditional',own/'conditional.py')
    api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
    geometry = dict(np.load(own/'geometry_GL32.npz'))
    law = read(own/'preparation.json')['phase_prior']
    selected = np.unique([int(np.argmin(abs(geometry['nodes']-(law['location']+offset)))) for offset in (-.1,0,.1)])
    small = {key:values[selected] for key,values in geometry.items()}
    errors = []
    for arm in ('c0','fitted_c'):
        arrays = dict(np.load(here/(arm+'_input.npz')))
        assert list(arrays['native_ids']) == full_ids
        parent = read(here/(arm+'_parent.json'))
        assert not parent['removed_curved_ids'] and not parent['removed_predictive_ids']
        assert parent['phase_qualified'] and parent['precision_qualified'] and parent['support_qualified']
        assert not set(full_ids) & (set(parent['calibration_ids']) | set(parent['predictive_ids']))
        for fold in folds:
            train,held = np.array(fold['train_indices']),np.array(fold['held_indices'])
            for physical in (False,True):
                modes = small['modes'] if physical else np.zeros((len(selected),29,0))
                oracle = conditional_oracle(arrays['raw'],arrays['covariance'],small['frequency'],modes,
                    small['log_prior_weights']+np.log(9),train,held,1/4.4e-6,np.arange(-4,5))
                actual = api.evaluate(arrays['raw'],arrays['covariance'],small,train,held,physical,1/4.4e-6)
                score = abs(actual['held_negative_twice_log_density']+2*oracle['log_density'])
                mean = float(np.max(abs(actual['prediction_mean']-oracle['mean'])))
                covariance = float(np.max(abs(actual['prediction_covariance']-oracle['covariance'])))
                assert score <= 1e-6 and mean <= 1e-6
                np.testing.assert_allclose(actual['prediction_covariance'],oracle['covariance'],rtol=1e-10,atol=1e-3)
                assert np.max(abs(actual['posterior_node_alias_mass'].ravel()-oracle['weights'])) <= 1e-10
                errors.append(dict(arm=arm,fold=fold['name'],physical_modes=physical,
                    score_error=score,mean_error_Hz=mean,covariance_error_Hz2=covariance))
    result = subprocess.run([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',
        str(own/'test_conditional.py'),str(own/'test_noise02.py')],capture_output=True,text=True,
        timeout=40,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    assert result.returncode == 0, result.stdout+result.stderr
    assert bindings(protocol['bindings']) == checked
    save('prediction_preflight02.json',dict(all_passed=True,
        protocol_sha256=sha(here/'protocol.json'),frozen_bindings_checked=checked,
        target_excluded_from_noise_training=True,noise_samples_removed=29,
        entire_pipeline_held_response_redactions=8,independent_dense_actual_port_checks=errors,
        charged_scientific_prefix_seconds=prefix,test_stdout=result.stdout,test_stderr=result.stderr,
        audit_seconds=time.monotonic()-began,new_orbit_propagations=0,new_fits=0,
        scope='Train-only conditional prediction given historically exposed fixed position/identity/graph/margin design, not independent identity or end-to-end validation.'))


def prediction_terminal02():
    began = time.monotonic()
    own = ROOT/'prediction'; here = own/'run02'
    protocol = read(here/'protocol.json'); seal = read(here/'RF_seal.json')
    checked = bindings(protocol['bindings'])+bindings(seal['files'])
    assert seal['protocol_sha256'] == sha(here/'protocol.json')
    execution = read(here/'execution.json')
    assert len(execution['slots']) == 8 and execution['cumulative_worker_seconds'] <= 300
    assert not execution['GPS_used'] and execution['position_fits'] == execution['identity_admissions'] == 0
    geometry = {order:dict(np.load(own/f'geometry_GL{order}.npz')) for order in (32,64)}
    by = {}; summaries = []; maximum_node_weight_error = 0.
    for slot in execution['slots']:
        arm,fold,model = slot['arm'],slot['fold'],slot['model']
        prefix = arm+'_'+fold+'_'+model
        if slot['status'] != 'complete':
            summaries.append(dict(arm=arm,fold=fold,model=model,status=slot['status'])); continue
        result = read(here/(prefix+'_result.json'))
        assert result['status'] == 'complete' and not result['held_values_used_for_training']
        assert result['inherited_noise_training_excludes_whole_D']
        assert not result['independent_identity_validation'] and not result['position_fit']
        actual_input = dict(np.load(here/(arm+'_input.npz')))
        train,held = np.array(result['train_indices']),np.array(result['held_indices'])
        values = {}
        for order in (32,64):
            scalar = read(here/(prefix+f'_GL{order}.json'))
            arrays = dict(np.load(here/(prefix+f'_GL{order}.npz')))
            weights = arrays['posterior_node_alias_mass']; geo = geometry[order]
            assert weights.shape == (len(geo['nodes']),9) and np.min(weights) >= 0
            assert abs(weights.sum()-1) < 1e-10
            phase_mean = weights.sum(axis=1) @ geo['nodes']
            phase_sd = np.sqrt(max(0.,weights.sum(axis=1) @ geo['nodes']**2-phase_mean**2))
            assert abs(phase_mean-scalar['phase_mean_s']) < 1e-10
            assert abs(phase_sd-scalar['phase_SD_s']) < 1e-8
            np.testing.assert_allclose(weights.sum(axis=0),scalar['alias_probabilities'],rtol=0,atol=1e-10)
            assert abs(scalar['held_negative_twice_log_density']+2*(scalar['joint_log_evidence']-scalar['train_log_evidence'])) <= 2e-6
            covariance = arrays['prediction_covariance']
            np.linalg.cholesky(covariance)
            np.testing.assert_allclose(arrays['prediction_SD']**2,np.diag(covariance),rtol=1e-12,atol=1e-8)
            residual = actual_input['raw'][held]-arrays['prediction_mean']
            np.testing.assert_array_equal(residual,arrays['held_raw_residual'])
            assert abs(np.sqrt(np.mean(residual**2))-scalar['raw_RMS_Hz']) < 1e-10
            assert abs(np.max(abs(residual)/arrays['prediction_SD'])-scalar['maximum_absolute_predictive_z']) < 1e-10
            # Sparse dense TRAIN likelihood oracle. This is not another integral.
            indices = np.unique([0,int(np.argmax(weights.sum(axis=1))),len(weights)-1])
            for node in indices:
                B = geo['modes'][node] if model == 'three_modes' else np.zeros((29,0))
                S = actual_input['covariance']+B@B.T
                TT = S[np.ix_(train,train)]
                for alias in range(-4,5):
                    raw = actual_input['raw'][train]+alias*(1/4.4e-6)-geo['frequency'][node,train]
                    expected = math.exp(geo['log_prior_weights'][node]+log_normal(raw,TT)-scalar['train_log_evidence'])
                    error = abs(expected-weights[node,alias+4]); maximum_node_weight_error = max(maximum_node_weight_error,error)
                    assert error <= 1e-9
            values[order] = dict(scalar,**arrays)
        a,b = values[32],values[64]; tolerance = protocol['tolerances']
        checks = dict(held_score=abs(a['held_negative_twice_log_density']-b['held_negative_twice_log_density'])<=tolerance['score'],
            train_score=abs(a['train_log_evidence']-b['train_log_evidence'])<=tolerance['score'],
            phase=abs(a['phase_mean_s']-b['phase_mean_s'])<=tolerance['phase'] and abs(a['phase_SD_s']-b['phase_SD_s'])<=tolerance['phase'],
            alias=np.max(abs(np.array(a['alias_probabilities'])-b['alias_probabilities']))<=tolerance['alias'],
            prediction=np.max(abs(a['prediction_mean']-b['prediction_mean']))<=tolerance['prediction_Hz'] and np.max(abs(a['prediction_SD']-b['prediction_SD']))<=tolerance['prediction_Hz'],
            shape=not len(a['shape_mean']) or np.max(abs(np.array(a['shape_mean'])-b['shape_mean']))<=tolerance['shape'],
            constant=abs(a['source_constant_mean_Hz']-b['source_constant_mean_Hz'])<=tolerance['constant_Hz'],
            conditional_identity=max(a['joint_conditional_identity_error'],b['joint_conditional_identity_error'])<=tolerance['conditional_identity'])
        assert checks == result['checks'] and all(checks.values()) == result['numerically_qualified']
        assert slot['qualified'] == result['numerically_qualified']
        by[arm,fold,model] = b
        summaries.append(dict(arm=arm,fold=fold,model=model,status='complete',qualified=result['numerically_qualified'],
            held_negative_twice_log_density=b['held_negative_twice_log_density'],held_RMS_Hz=b['raw_RMS_Hz'],
            phase_mean_s=b['phase_mean_s'],phase_SD_s=b['phase_SD_s']))
    gains = [dict(arm=arm,fold=fold,held_NLL_nominal_minus_three_modes=by[arm,fold,'nominal']['held_negative_twice_log_density']-
        by[arm,fold,'three_modes']['held_negative_twice_log_density'])
        for arm in ('c0','fitted_c') for fold in protocol['folds'] if (arm,fold,'nominal') in by and (arm,fold,'three_modes') in by]
    save('prediction_terminal02.json',dict(all_passed=True,
        protocol_sha256=sha(here/'protocol.json'),RF_seal_sha256=sha(here/'RF_seal.json'),
        frozen_bindings_checked=checked,complete_slots=sum(q['status']=='complete' for q in execution['slots']),
        planned_slots=8,posterior_moments_and_density_checks=True,maximum_sparse_dense_node_weight_error=maximum_node_weight_error,
        summaries=summaries,paired_model_gains=gains,cumulative_scientific_worker_seconds=execution['cumulative_worker_seconds'],
        audit_seconds=time.monotonic()-began,new_orbit_propagations=0,new_fits=0,new_phase_integrals=0,
        scope='Conditional temporal prediction within one previously selected owner; folds/arms are dependent and do not validate identity, admission or localization.'))


if __name__ == '__main__':
    globals()[sys.argv[1]]()
