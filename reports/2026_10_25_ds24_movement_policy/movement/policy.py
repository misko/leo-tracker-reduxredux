"""Deterministic paired policy; no fitting, geographic truth, or tuned thresholds."""
import numpy as np

from common import ARMS, MODELS, SCALES, SEEDS, finite_numeric_tree


def job_failures(result):
    reasons = []
    if result.get('status') != 'complete':
        return ['job_' + result.get('status', 'missing')]
    if not finite_numeric_tree(result):
        reasons.append('nonfinite_job')
    for arm in ARMS:
        analysis = result.get('arms', {}).get(arm, {})
        for model in MODELS:
            fit = analysis.get('fits', {}).get(model)
            if fit is None:
                reasons.append(f'{arm}/{model}/missing_fit')
                continue
            if fit['final_phase_change_s'] > .01:
                reasons.append(f'{arm}/{model}/train_phase')
            if fit['training_final_log_precision_change'] > 1e-5:
                reasons.append(f'{arm}/{model}/train_gamma')
            terminal = fit['history'][-1]['fit']['stopped']
            if terminal not in ('small_step_and_improvement', 'no_accepted_damped_step'):
                reasons.append(f'{arm}/{model}/position_{terminal}')
            x = np.asarray(fit['endpoint_east_north_km'])
            if x.shape != (2,) or not np.isfinite(x).all() or np.any(abs(x) > 12.5 + 1e-8):
                reasons.append(f'{arm}/{model}/invalid_endpoint')
        for predictor in MODELS:
            for endpoint in MODELS:
                prediction = analysis.get('crossover', {}).get(predictor, {}).get(endpoint)
                prefix = f'{arm}/{predictor}/at_{endpoint}'
                if prediction is None:
                    reasons.append(prefix + '/missing_prediction')
                    continue
                if prediction['phase_refresh_changes_s'][-1] > .01:
                    reasons.append(prefix + '/fixed_phase')
                if prediction['final_log_precision_change'] > 1e-5:
                    reasons.append(prefix + '/fixed_gamma')
                for scale in SCALES:
                    if str(scale) not in prediction['scores']:
                        reasons.append(prefix + '/missing_scale')
    return reasons


def gain_rows(results, case):
    rows = []
    for seed in SEEDS:
        partition = {r['fold']: r for r in results if r.get('case') == case and r.get('seed') == seed}
        for arm in ARMS:
            for predictor in MODELS:
                for scale in SCALES:
                    gains, quadratic, logdet = [], [], []
                    for fold in range(3):
                        result = partition.get(fold, {})
                        if result.get('status') != 'complete':
                            continue
                        try:
                            scores = result['arms'][arm]['crossover'][predictor]
                            a, b = [scores[m]['scores'][str(scale)] for m in MODELS]
                            gains.append(a['negative_twice_log_density'] - b['negative_twice_log_density'])
                            quadratic.append(a['quadratic'] - b['quadratic'])
                            logdet.append(a['logdet'] - b['logdet'])
                        except KeyError:
                            continue
                    valid = len(gains) == 3 and np.isfinite(gains + quadratic + logdet).all()
                    rows.append(dict(case=case, seed=seed, arm=arm, predictor=predictor,
                        sigma_multiplier=scale, complete_folds=len(gains),
                        gain=float(sum(gains)) if valid else None,
                        quadratic_gain=float(sum(quadratic)) if valid else None,
                        logdet_gain=float(sum(logdet)) if valid else None,
                        fold_gains=[float(g) if np.isfinite(g) else None for g in gains],
                        positive_folds=sum(g > 0 for g in gains)))
    return rows


def decide(case, results, full_data):
    """Return one pair source and every failed requirement; never mix c arms."""
    reasons = []
    if not full_data['eligible']:
        reasons.append('original_RF_unqualified')
    if not full_data['original_adopted']:
        reasons.append('original_policy_baseline')
    if not full_data['original_paired_gates_pass']:
        reasons.append('original_paired_gates_failed')
    required = {(seed, fold) for seed in SEEDS for fold in range(3)}
    observed = [(r.get('seed'), r.get('fold')) for r in results if r.get('case') == case]
    if len(observed) != 6 or set(observed) != required:
        reasons.append('missing_or_duplicate_jobs')
    for result in results:
        if result.get('case') == case:
            prefix = f"seed{result.get('seed')}/fold{result.get('fold')}"
            reasons.extend(prefix + '/' + reason for reason in job_failures(result))
    aggregate = gain_rows(results, case)
    for row in aggregate:
        if row['gain'] is None or not np.isfinite(row['gain']) or row['gain'] <= 1e-8:
            reasons.append(f"seed{row['seed']}/{row['arm']}/{row['predictor']}/sigma{row['sigma_multiplier']}/nonpositive_or_missing_gain")
    source = 'sharedRF50' if not reasons else 'baseline'
    return dict(case=case, adopted=not reasons, policy_source=source,
        failure_reasons=reasons, aggregate_gains=aggregate,
        endpoint_pair=full_data['candidate_pair'] if not reasons else full_data['baseline_pair'],
        exact_pair_source_binding=full_data['candidate_binding'] if not reasons else full_data['baseline_binding'],
        original_policy_source='sharedRF50' if full_data['original_adopted'] else 'baseline',
        original_policy_endpoint_pair=full_data['candidate_pair'] if full_data['original_adopted'] else full_data['baseline_pair'])
