"""Independent saved-vector and paired-policy reconstruction; never fit or use GPS."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ARMS = ('c0', 'fitted_c')
MODELS = ('baseline', 'sharedRF50')
SEEDS = (2026102504, 2026102505)
SCALES = (1., float(np.sqrt(2.)), 2.)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def score_svd_all_scales(raw, uncertainty, sigma):
    """One independent observation-space SVD; exact rescaling for all three noises."""
    b = raw/sigma
    left, singular, _ = np.linalg.svd(uncertainty/sigma[:, None], full_matrices=False)
    projected = left.T @ b
    remainder = b-left@projected
    remainder_norm = float(remainder@remainder)
    outputs = {}
    for scale in SCALES:
        quadratic = float(remainder_norm/scale**2 + np.sum((projected/scale)**2/(1+(singular/scale)**2)))
        logdet = float(2*np.log(sigma).sum()+2*len(raw)*np.log(scale)+np.log1p((singular/scale)**2).sum())
        outputs[str(scale)] = dict(quadratic=quadratic, logdet=logdet,
            negative_twice_log_density=quadratic+logdet+len(raw)*np.log(2*np.pi),
            mean_prediction_RMS_hz=float(np.sqrt(np.mean(raw**2))))
    return outputs


def check_frozen_inputs():
    movement = ROOT/'movement'
    protocol = read(movement/'protocol.json')
    seal = read(movement/'freeze_seal.json')
    assert sha(movement/'protocol.json') == seal['protocol_sha256']
    for binding in protocol['bindings']:
        assert sha(binding['path']) == binding['sha256'], binding['path']
    original = read(HERE/'baseline_membership.json')['cases']
    manifest = read(movement/'input_manifest.json')
    full_data = read(movement/'full_data_bindings.json')
    study = read(ROOT/'protocol.json')
    assert protocol['cases'] == study['cases']
    assert protocol['jobs'] == study['job_dispatch']
    assert protocol['seeds'] == list(SEEDS)
    assert protocol['models'] == list(MODELS) and protocol['arms'] == list(ARMS)
    assert protocol['sigma_multipliers'] == list(SCALES)
    assert protocol['gain_tolerance'] == 1e-8
    assert protocol['phase_tolerance_s'] == .01 and protocol['gamma_log_precision_tolerance'] == 1e-5
    assert protocol['GPS_used'] is False and protocol['new_RF'] is False
    assert protocol['job_seconds_cap'] == 240 and protocol['batch_seconds_cap'] == 2700
    assert protocol['phase_rounds'] == 5 and protocol['position_steps'] == 48
    for case, item in manifest.items():
        old = original[case]
        assert item['baseline_sha256'] == old['baseline_sha256']
        assert item['measurement_binding_sha256'] == old['measurement_binding_sha256']
        family = {r['candidate_index']: r for r in old['family_membership']}
        curved = set().union(*(set(r['curved_ids']) for r in family.values()))
        predictive = set().union(*(set(r['predictive_ids']) for r in family.values()))
        assert curved.isdisjoint(predictive)
        labels = sorted(family)
        assert item['inherited_full_RF_fixed_noise']['per_observation_noise_sigma_hz'] == old['native_sigma']
        for seed in SEEDS:
            part = item['partitions'][str(seed)]
            rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, int(case.split('-')[-1])])))
            permutation = rng.permutation(np.array(labels, int))
            expected = [sorted(map(int, g)) for g in np.array_split(permutation, 3)]
            assert part['active_family_indices'] == labels
            assert part['permutation'] == permutation.tolist()
            held_all = []
            for fold, held in zip(part['folds'], expected, strict=True):
                assert fold['held_families'] == held
                held_curved = set().union(*(set(family[j]['curved_ids']) for j in held))
                held_predictive = set().union(*(set(family[j]['predictive_ids']) for j in held))
                for key, ids in [('curved_held_ids', held_curved), ('predictive_held_ids', held_predictive),
                                 ('curved_training_ids', curved-held_curved), ('predictive_training_ids', predictive-held_predictive)]:
                    assert set(fold[key]) == ids and len(fold[key]) == len(ids), (case, seed, fold['fold'], key)
                for prefix in ('training', 'held'):
                    ids = fold['curved_'+prefix+'_ids']+fold['predictive_'+prefix+'_ids']
                    assert hashlib.sha256(canonical(ids)).hexdigest() == fold[prefix+'_ids_sha256']
                held_all += fold['curved_held_ids']+fold['predictive_held_ids']
            assert len(held_all) == len(set(held_all)) == len(curved)+len(predictive)
            assert set(held_all) == curved|predictive
        saved = read(full_data[case]['baseline_binding']['path'])
        rx = read(full_data[case]['candidate_binding']['path'])
        assert sha(full_data[case]['baseline_binding']['path']) == full_data[case]['baseline_binding']['sha256'] == old['baseline_sha256']
        assert sha(full_data[case]['candidate_binding']['path']) == full_data[case]['candidate_binding']['sha256']
        assert full_data[case]['eligible'] == rx['eligible']
        assert full_data[case]['original_adopted'] == rx['adopted']
        assert full_data[case]['original_paired_gates_pass'] == rx['paired_valid']
        assert rx['adopted'] == (rx['eligible'] and rx['paired_valid'] and rx['status'] == 'complete')
        assert (rx['policy_source'] == 'trial') == rx['adopted']
        for arm in ARMS:
            assert full_data[case]['baseline_pair'][arm] == saved['policy_arms'][arm]['endpoint_east_north_km']
            assert full_data[case]['candidate_pair'][arm] == rx['arms'][arm]['endpoint_east_north_km']
    return protocol, manifest, full_data, original


def audit_complete(case_filter=None):
    protocol, manifest, full_data, original = check_frozen_inputs()
    movement = ROOT/'movement'
    result_bindings, score_rows, job_rows = [], [], []
    max_difference = 0.
    fits = vectors = 0
    cases = {}
    selected_cases = protocol['cases'] if case_filter is None else [case_filter]
    assert set(selected_cases) <= set(protocol['cases'])
    for case in selected_cases:
        old = original[case]
        family = {r['candidate_index']: r for r in old['family_membership']}
        result_rows = []
        for seed in SEEDS:
            for fold in range(3):
                path = movement/'results'/f'{case}_seed{seed}_fold{fold}.json'
                saved = read(path)
                result_bindings.append(dict(path=str(path), sha256=sha(path)))
                assert (saved['case'], saved['seed'], saved['fold']) == (case, seed, fold)
                assert saved['GPS_used'] is False and saved['protocol_sha256'] == sha(movement/'protocol.json')
                assert saved['source_sha256'] == sha(movement/'movement.py')
                assert saved['kernel_sha256'] == sha(movement/'kernel.py')
                result_rows.append(saved)
                failures = []
                if saved['status'] != 'complete':
                    failures.append(saved['status'])
                    job_rows.append(dict(case=case, seed=seed, fold=fold, status=saved['status'], failures=failures))
                    continue
                assert saved['baseline_sha256'] == old['baseline_sha256']
                assert saved['input_binding_sha256'] == old['measurement_binding_sha256']
                frozen = manifest[case]['partitions'][str(seed)]['folds'][fold]
                held = frozen['held_families']
                assert saved['held_families'] == held
                expected_ids = set(frozen['curved_held_ids']+frozen['predictive_held_ids'])
                for arm in ARMS:
                    data = saved['arms'][arm]
                    assert set(data['fits']) == set(MODELS)
                    for model in MODELS:
                        fitted = data['fits'][model]
                        fits += 1
                        assert len(fitted['history']) == 5
                        assert fitted['training_curved_points'] == len(frozen['curved_training_ids'])
                        assert fitted['training_predictive_points'] == len(frozen['predictive_training_ids'])
                        if fitted['final_phase_change_s'] > .01: failures.append(f'{arm}/{model}/train_phase')
                        if fitted['training_final_log_precision_change'] > 1e-5: failures.append(f'{arm}/{model}/train_gamma')
                        stopped = fitted['history'][-1]['fit']['stopped']
                        if stopped not in ('small_step_and_improvement', 'no_accepted_damped_step'): failures.append(f'{arm}/{model}/position_{stopped}')
                        assert np.isfinite(fitted['endpoint_east_north_km']).all()
                        assert max(abs(np.asarray(fitted['endpoint_east_north_km']))) <= 12.5+1e-8
                    for predictor in MODELS:
                        for endpoint in MODELS:
                            vector = data['crossover'][predictor][endpoint]
                            if vector['phase_refresh_changes_s'][-1] > .01: failures.append(f'{arm}/{predictor}/{endpoint}/fixed_phase')
                            if vector['final_log_precision_change'] > 1e-5: failures.append(f'{arm}/{predictor}/{endpoint}/fixed_gamma')
                            assert sha(vector['artifact']) == vector['artifact_sha256']
                            with np.load(vector['artifact'], allow_pickle=False) as a:
                                raw, uncertainty, sigma = a['raw'], a['uncertainty'], a['native_sigma']
                                ids = a['observation_ids'].tolist()
                                assert len(ids) == len(set(ids)) and set(ids) == expected_ids
                                assert hashlib.sha256(canonical(ids)).hexdigest() == vector['observation_id_sha256'] == frozen['held_ids_sha256']
                                np.testing.assert_array_equal(sigma, [old['native_sigma'][oid] for oid in ids])
                                np.testing.assert_array_equal(a['position'], data['fits'][endpoint]['endpoint_east_north_km'])
                                slots = [old['labels'].index(j) for j in held]
                                np.testing.assert_array_equal(a['reference'][slots], np.asarray(old['phase_prior_means_s'])[slots])
                                for j in held:
                                    assert set(np.asarray(ids)[a['family'] == j]) == set(family[j]['curved_ids']+family[j]['predictive_ids'])
                                restored = np.linalg.solve(a['posterior_precision_cholesky'], a['held_design'].T).T
                                restored = np.column_stack((restored, a['predictive_fragment_constants']))
                                np.testing.assert_allclose(restored, uncertainty, rtol=1e-11, atol=1e-10)
                                scores = score_svd_all_scales(raw, uncertainty, sigma)
                                for scale in SCALES:
                                    declared = vector['scores'][str(scale)]
                                    for key, value in scores[str(scale)].items():
                                        difference = abs(value-declared[key])
                                        max_difference = max(max_difference, difference)
                                        assert difference < 1e-5, (case, seed, fold, arm, predictor, endpoint, scale, key, difference)
                                    score_rows.append(dict(case=case, seed=seed, fold=fold, arm=arm,
                                        predictor=predictor, endpoint=endpoint, sigma_multiplier=scale,
                                        **scores[str(scale)]))
                            assert vector['prior_audit']['maximum_held_training_loading'] == 0
                            assert vector['prior_audit']['maximum_held_trained_crosscovariance'] <= 1e-12
                            np.testing.assert_allclose(vector['prior_audit']['held_phase_variance'], 1., rtol=0, atol=1e-12)
                            vectors += 1
                job_rows.append(dict(case=case, seed=seed, fold=fold, status='complete', failures=sorted(set(failures))))
        all_valid = all(not row['failures'] for row in job_rows if row['case'] == case)
        aggregates = []
        for seed in SEEDS:
            for arm in ARMS:
                for predictor in MODELS:
                    for scale in SCALES:
                        rows = [r for r in score_rows if (r['case'], r['seed'], r['arm'], r['predictor'], r['sigma_multiplier']) == (case, seed, arm, predictor, scale)]
                        gain = None
                        if len(rows) == 6:
                            gain = sum((1 if r['endpoint'] == 'baseline' else -1)*r['negative_twice_log_density'] for r in rows)
                        aggregates.append(dict(seed=seed, arm=arm, predictor=predictor, sigma_multiplier=scale, gain=gain))
        eligible = all(full_data[case][key] for key in ('eligible', 'original_adopted', 'original_paired_gates_pass'))
        adopted = eligible and all_valid and all(r['gain'] is not None and r['gain'] > 1e-8 for r in aggregates)
        cases[case] = dict(adopted=bool(adopted), original_eligible=eligible, all_jobs_valid=all_valid,
            endpoint_pair=full_data[case]['candidate_pair' if adopted else 'baseline_pair'], aggregates=aggregates)
        print('audited', case, 'adopted', bool(adopted), 'vectors', vectors, flush=True)
    output = dict(status='passed', GPS_used=False, no_position_fitting=True, source_sha256=sha(Path(__file__)),
        movement_protocol_sha256=sha(movement/'protocol.json'), root_protocol_sha256=sha(ROOT/'protocol.json'),
        position_fits=fits, covariance_vectors=vectors, sensitivity_scores=len(score_rows),
        maximum_saved_score_difference=max_difference, cases=cases, job_rows=job_rows,
        result_bindings=result_bindings, independent_scores='Observation-space SVD with shared singular vectors across noise scales')
    destination = HERE if case_filter is None else HERE/'movement_cases'
    destination.mkdir(exist_ok=True)
    prefix = 'movement_artifacts' if case_filter is None else case_filter
    score_name = 'independent_scores.csv' if case_filter is None else case_filter+'_scores.csv'
    output['partial_diagnostic_only'] = case_filter is not None
    write_new(destination/(prefix+'.json'), output)
    with (destination/score_name).open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(score_rows[0]))
        writer.writeheader(); writer.writerows(score_rows)
    print(json.dumps({k:v for k,v in output.items() if k not in ('cases', 'job_rows', 'result_bindings')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs-only', action='store_true')
    parser.add_argument('--case')
    args = parser.parse_args()
    if args.inputs_only:
        protocol, manifest, _, _ = check_frozen_inputs()
        write_new(HERE/'movement_input_audit.json', dict(status='passed', GPS_used=False, no_position_fits=True,
            movement_protocol_sha256=sha(ROOT/'movement/protocol.json'), cases=len(manifest), partitions=2*len(manifest),
            source_sha256=sha(Path(__file__)), source_and_test_review_still_required=True))
    else:
        audit_complete(args.case)
