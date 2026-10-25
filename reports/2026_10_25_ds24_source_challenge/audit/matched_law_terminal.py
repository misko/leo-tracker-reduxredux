"""Artifact-only audit of injected observations, frozen backgrounds and orders."""
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp
from scipy.stats import t

HERE = Path(__file__).resolve().parent
LAW = HERE.parent / 'matched_law'
sys.path.insert(0, str(LAW))
import control as c

read = lambda path: json.loads(Path(path).read_bytes())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
digest = lambda value: hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def order(rows, null):
    if not null['independent_dense_passed']:
        return False, None, None
    candidates = [(None, -.5 * (null['objective'] + 1e-6), -.5 * (null['objective'] - 1e-6))]
    for row in rows:
        if row.get('status') == 'zero_physical_evidence' and row.get('empty_support_certified') and row.get('certified_visibility'):
            candidates.append((row['norad'], -np.inf, -np.inf)); continue
        lo, hi = row.get('full_support_lower_log_integral'), row.get('full_support_upper_log_integral')
        if not row.get('certified_visibility') or lo is None or hi is None or not np.isfinite([lo, hi]).all() or lo > hi:
            return False, None, None
        candidates.append((row['norad'], lo, hi))
    for norad, lo, hi in candidates:
        upper = max(x[2] for x in candidates if x[0] != norad)
        if lo > upper:
            return True, norad, lo - upper
    return False, None, None


def main():
    start = time.monotonic(); checks = []; outcomes = []; forward = []; gaussian_errors = []; counted = 0
    def check(name, passed, **detail):
        checks.append(dict(name=name, passed=bool(passed), **detail))
    protocol = read(LAW / 'protocol.json'); seal = read(LAW / 'RF_seal.json')
    check('frozen protocol, preflight, all source/input/context/output bytes exact',
          sha(LAW / 'protocol.json') == seal['protocol_sha256'] == read(HERE / 'matched_law_preflight.json')['protocol_sha256'] and
          read(HERE / 'matched_law_preflight.json')['all_passed'] and
          all(sha(path) == h for path, h in protocol['files'].items()) and
          all(sha(path) == h for path, h in seal['files'].items()))
    execution = read(LAW / 'execution.json')
    cumulative = protocol['preparation_seconds'] + protocol['test_seconds'] + sum(row['seconds'] for row in execution['cases'])
    check('six vector/twelve arm slots and all processing charged within600s',
          execution['total_vectors'] == 6 and execution['arm_trial_slots'] == 12 and
          cumulative == execution['worker_seconds'] <= 600 and execution['position_fits'] == 0 and not execution['GPS_used'],
          cumulative_scientific_seconds=cumulative)
    for case in ('DS24-0010', 'DS24-0011'):
        meta = read(LAW / case / 'context.json')
        with np.load(LAW / case / 'context.npz') as saved:
            data = {key: saved[key].copy() for key in saved.files}
        child_execution = read(LAW / case / 'execution.json')
        check(case + ': exact6 terminal arm/trial denominator, failures retained',
              {(row['arm'], row['trial']) for row in child_execution['results']} == {(a, j) for a in c.ARMS for j in range(3)} and
              child_execution['all_selected_arm_trial_slots'] == 6 and child_execution['position_fits'] == 0 and not child_execution['GPS_used'])
        for trial in range(3):
            root = LAW / case / ('trial' + str(trial))
            if not (root / 'observations.npz').exists():
                check(case + '/trial' + str(trial) + ': unavailable draw explicitly retained',
                      all(row['status'] == 'unavailable' for row in child_execution['results'] if row['trial'] == trial))
                continue
            counted += 1
            truth = read(root / 'truth.json')
            with np.load(root / 'observations.npz') as archive:
                values = archive['values_Hz'].copy()
                check(case + '/trial' + str(trial) + ': whole layout IDs/times unchanged',
                      np.array_equal(archive['native_ids'], data['native_ids']) and np.array_equal(archive['times_s'], data['times_s']))
            children = np.random.SeedSequence([c.SEED, int(case[-4:]), trial]).spawn(4)
            generators = [np.random.Generator(np.random.PCG64(s)) for s in children]
            uniform = float(generators[0].uniform())
            factor = np.array(truth['physical_or_null_factor_Hz'])
            z = generators[1].normal(size=factor.shape[1]); noise_z = generators[2].normal(size=len(values))
            alias = int(generators[3].choice(np.arange(-4, 5)))
            noise = np.linalg.cholesky(data['c0_covariance_Hz2']) @ noise_z
            mean = np.array(truth['physical_or_null_mean_Hz'])
            reconstructed = data['c0_radio_mean_Hz'] + mean + factor @ z + noise - alias * c.lm.PERIOD
            error = float(np.max(abs(values - reconstructed))); forward.append(error)
            check(case + '/trial' + str(trial) + ': independent seed streams and full c0 observation injection closure',
                  truth['phase_uniform'] == uniform and truth['alias'] == alias and
                  np.array_equal(truth['latent_z'], z) and np.array_equal(truth['noise_z'], noise_z) and
                  np.allclose(truth['noise_Hz'], noise, atol=1e-10, rtol=0) and error <= 1e-9 and
                  truth['c0_matching_law'] and truth['fitted_c_off_law'])
            if trial < 2:
                j = meta['pair_indices'][trial]
                law = meta['selected_phase_laws'][trial]
                distribution = t(3, loc=law['location'], scale=law['original_marginal_SD'] / np.sqrt(3))
                phase = float(distribution.ppf(distribution.cdf(-15) + uniform * law['domain_mass']))
                check(case + '/trial' + str(trial) + ': declared full-visible physical identity/Student phase law',
                      truth['kind'] == 'physical' and truth['candidate_index'] == j and truth['norad'] == int(data['norads'][j]) and
                      abs(truth['phase_s'] - phase) < 1e-12 and factor.shape == (len(values), 3) and -15 <= phase <= 15)
            else:
                check(case + '/trial2: exact frozen proper near-null mean/factor rather than refitted null',
                      truth['kind'] == 'near_null' and truth['norad'] is None and
                      np.array_equal(mean, data['null_mean_Hz']) and np.array_equal(factor, data['null_factor_Hz']))
            screens = {arm: read(root / (arm + '_ordinary_screen.json')) for arm in c.ARMS}
            for arm in c.ARMS:
                screen = screens[arm]
                score = np.array([np.inf if v is None else v for v in screen['coarse_scores']])
                ranked = sorted(np.flatnonzero(np.isfinite(score)), key=lambda j: (float(score[j]), int(data['norads'][j])))
                check(case + '/trial' + str(trial) + '/' + arm + ': ordinary complete catalogue rank and actual injected-response fingerprint',
                      screen['candidate_indices'] == ranked[:8] and screen['ranked_visible_indices'] == ranked and
                      screen['candidate_norads'] == data['norads'][ranked[:8]].tolist() and
                      not screen['forced_or_reserved_candidate'] and
                      screen['screen_observation_sha256'] == digest(values - data[arm + '_radio_mean_Hz']))
                result = read(root / arm / 'result.json')
                check(case + '/trial' + str(trial) + '/' + arm + ': terminal record retains original outcome/status',
                      result == next(row for row in child_execution['results'] if row['trial'] == trial and row['arm'] == arm))
                pool = screens['c0']['candidate_indices']
                records = result.get('candidates', [])
                if result['status'] != 'unavailable':
                    check(case + '/trial' + str(trial) + '/' + arm + ': identical c0 pool in both arms, no oracle backfill',
                          [row['candidate_index'] for row in result['ordinary_candidate_slots']] == pool and
                          [row['candidate_index'] for row in records] == pool[:len(records)] and
                          all(row['ordinary_shortlist_member'] for row in records) and
                          result['exact_matching_law'] == (arm == 'c0') and result['fitted_sensitivity_off_law'] == (arm != 'c0'))
                if 'null' in result:
                    null = result['null']; covariance = data[arm + '_covariance_Hz2'] + data['null_factor_Hz'] @ data['null_factor_Hz'].T
                    L = np.linalg.cholesky(covariance)
                    costs = []
                    for k in range(-4, 5):
                        white = solve_triangular(L, values - data[arm + '_radio_mean_Hz'] - data['null_mean_Hz'] + k * c.lm.PERIOD, lower=True)
                        costs.append(white @ white + 2 * np.log(np.diag(L)).sum() + len(values) * np.log(2 * np.pi))
                    expected = -2 * (logsumexp(-.5 * np.array(costs)) - np.log(9))
                    gaussian_errors.append(abs(expected - null['objective']))
                    check(case + '/trial' + str(trial) + '/' + arm + ': normalized shared-background null score exactly once',
                          abs(expected - null['objective']) <= 1e-7 and
                          null['independent_dense_passed'] == (abs(null['objective'] - null['reference_objective']) < 1e-6))
                for row in records + ([result['label_available_diagnostic']] if result.get('label_available_diagnostic') else []):
                    support = row['support']
                    objective = row.get('objective'); lo = row.get('full_support_lower_log_integral'); hi = row.get('full_support_upper_log_integral')
                    error = max(abs(objective + 2 * lo), abs(objective + 2 * hi)) if objective is not None and lo is not None and hi is not None else None
                    absolute = bool(row['empty_support_certified'] or support['certified'] and error is not None and error <= 1e-3)
                    check(case + '/trial' + str(trial) + '/' + arm + ': ' + str(row['norad']) + ' support/prior/precision flags consistent',
                          support['certified'] == row['certified_visibility'] and not row['visible_mass_renormalized'] and
                          row['mode_and_support_qualified'] == absolute and
                          row['numerically_qualified'] == bool(row['empty_support_certified'] or
                              row['mode_and_support_qualified'] and row['primary']['success'] and row['bracket_quadrature']['success']))
                if result['status'] == 'complete':
                    expected = order(records, result['null']); saved = result['ordinary_order']
                    check(case + '/trial' + str(trial) + '/' + arm + ': original finite-pool order rederived from full support bounds',
                          expected[0] == saved['proved'] and (not expected[0] or
                          saved['winner_norad'] == expected[1] and abs(saved['minimum_log_evidence_margin'] - expected[2]) < 1e-9 and
                          not saved['operational_identity_assignment'] and not saved['absolute_score_precision_implied']))
                    missing = truth['kind'] == 'physical' and truth['candidate_index'] not in pool
                    oracle = result.get('label_available_diagnostic')
                    oracle_order = order(records + ([oracle] if oracle else []), result['null'])
                    saved_oracle_order = result['label_available_order']
                    check(case + '/trial' + str(trial) + '/' + arm + ': available-label diagnostic remains separate',
                          result['ordinary_shortlist_unchanged'] and (oracle is not None) == missing and
                          (not missing or oracle['candidate_index'] == truth['candidate_index'] and not oracle['ordinary_shortlist_member']) and
                          oracle_order[0] == saved_oracle_order['proved'] and
                          (not oracle_order[0] or saved_oracle_order['winner_norad'] == oracle_order[1] and
                              abs(saved_oracle_order['minimum_log_evidence_margin'] - oracle_order[2]) < 1e-9) and
                          result['observation_sha256'] == digest(values) and
                          result['background_mean_sha256'] == digest(data[arm + '_radio_mean_Hz']) and
                          result['covariance_sha256'] == digest(data[arm + '_covariance_Hz2']))
                outcomes.append(dict(case=case, trial=trial, arm=arm, kind=truth['kind'], truth=truth['norad'],
                    shortlist=screen['candidate_norads'], exact_pool=screens['c0']['candidate_norads'],
                    truth_in_c0_pool=None if truth['kind'] != 'physical' else truth['candidate_index'] in pool,
                    truth_ordinary_rank=None if truth['kind'] != 'physical' else (ranked.index(truth['candidate_index']) + 1 if truth['candidate_index'] in ranked else None),
                    status=result['status'], scored_candidates=len(records), order=result.get('ordinary_order'),
                    label_available_order=result.get('label_available_order'),
                    absolute_precision_candidates=sum(row.get('numerically_qualified', False) for row in records)))
    check('six original vectors retained without redraw or replacement', counted == 6)
    seconds = time.monotonic() - start
    cumulative_audit = read(HERE / 'matched_law_preflight.json')['cumulative_audit_seconds'] + seconds
    receipt = dict(all_passed=all(row['passed'] for row in checks) and cumulative_audit <= 180,
        checks=checks, outcomes=outcomes, seconds=seconds, cumulative_audit_seconds=cumulative_audit,
        protocol_sha256=sha(LAW / 'protocol.json'), RF_seal_sha256=sha(LAW / 'RF_seal.json'), source_sha256=sha(__file__),
        maximum_recorded_forward_reconstruction_error_Hz=max(forward, default=0),
        maximum_independent_null_objective_error=max(gaussian_errors, default=0),
        new_catalogue_searches=0, new_physical_propagation_calls=0, new_scientific_vectors=0, position_fits=0, geographic_truth_read=False,
        scope='Recorded generating components/seed/CFO closure and full-support order arithmetic; no new physical propagation. c0 exact exogenous law, fitted-c off-law same observations. No shared-parent/GLRT-selection/false-association-rate calibration.')
    with (HERE / 'matched_law_terminal.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(all_passed=receipt['all_passed'], checks=len(checks), seconds=seconds,
        failed=[row for row in checks if not row['passed']], outcomes=outcomes)))


if __name__ == '__main__':
    main()
