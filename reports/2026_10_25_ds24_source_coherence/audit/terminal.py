"""Independent artifact-only audit; no propagation or scientific-score replay."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
SCI = HERE.parent / 'scientific'
RUN = SCI / 'run02'
OLD = Path('/srv/bulk/leo/research/ds24-ch5-prediction-r01/prediction/run02')
read = lambda p: json.loads(Path(p).read_bytes())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    start = time.monotonic(); checks = []; metrics = []
    def check(name, ok, **detail):
        checks.append(dict(name=name, passed=bool(ok), **detail))
    seal = read(RUN / 'RF_seal.json'); protocol = read(RUN / 'protocol.json')
    digest = sha(RUN / 'protocol.json')
    check('exact final protocol, approval and every RF-sealed artifact',
          digest == seal['protocol_sha256'] == read(HERE / 'preflight02.json')['protocol_sha256'] and
          read(HERE / 'preflight02.json')['all_passed'] and
          all(sha(path) == h for path, h in seal['files'].items()), files=len(seal['files']))
    check('every frozen source/input binding and failed first version remains exact',
          all(sha(path) == h for path, h in protocol['source_input_hashes'].items()) and
          all(sha(path) == h for path, h in read(SCI / 'RF_seal.json')['files'].items()))
    execution = read(RUN / 'execution.json')
    check('complete fixed denominator, no optimization or geography',
          execution['all_selected_terminal'] and execution['all100IDs_retained'] and
          execution['selected_arms'] == 2 and execution['selected_classes'] == 8 and
          execution['selected_model_contexts'] == 22 and execution['position_fits'] == 0 and
          execution['GPS_used'] is False and {row['arm'] for row in execution['arms']} == {'c0', 'fitted_c'})
    cumulative = sum(row['scientific_worker_seconds'] for row in execution['arms']) + \
        read(SCI / 'execution.json')['scientific_seconds'] + read(RUN / 'load_smoke.json')['scientific_worker_seconds']
    check('all failure/setup/science seconds accounted within original600s, no retry',
          cumulative == execution['cumulative_scientific_worker_seconds'] and cumulative <= 600 and
          execution['previous_failed_worker_seconds'] == 4.737606174312532 and
          all(row['scientific_worker_seconds'] <= protocol['worker_deadline_seconds'] for row in execution['arms']) and
          protocol['scientific_retries'] == 0, cumulative_worker_seconds=cumulative)
    positions = []
    period = 250000. / 1.1
    expected_names = {'whole_physical', 'whole_polynomial'} | {
        'cut' + str(cut) + '_' + label for cut in (14, 21, 29) for label in ('prefix', 'suffix', 'polynomial')}
    for arm in ('c0', 'fitted_c'):
        root = RUN / arm
        result = read(root / 'result.json')
        check(arm + ': all11 cells complete, result matches execution, no adoption',
              result == next(row for row in execution['arms'] if row['arm'] == arm) and
              result['status'] == 'complete' and len(result['models']) == 11 and
              {row['name'] for row in result['models']} == expected_names and
              result['all100IDs_scored'] and not result['portion_adopted'] and
              not result['identity_assignment'] and result['position_fits'] == 0 and not result['GPS_used'])
        with np.load(root / 'inputs.npz') as actual, np.load(OLD / arm / 'joint_background.npz') as saved:
            ix = np.r_[np.arange(57), np.arange(81, 124)]
            for key, expected in [('raw_hz', saved['raw_hz'][ix]),
                                  ('covariance_hz2', saved['covariance_hz2'][np.ix_(ix, ix)]),
                                  ('native_q', saved['native_q'][ix]), ('native_ids', saved['native_ids'][ix]),
                                  ('times_s', saved['times_s'][ix]),
                                  ('common_position_east_north_km', saved['common_position_east_north_km'])]:
                check(arm + ': exact archived ' + key, np.array_equal(actual[key], expected))
            ids = actual['native_ids']; sigma = actual['native_sigma_Hz'].copy()
            check(arm + ': all100 distinct nativeIDs, finite original noise and RF scales',
                  len(ids) == len(set(ids)) == 100 and np.isfinite(sigma).all() and np.all(sigma > 0) and
                  np.isfinite(actual['native_q']).all() and np.all(actual['native_q'] > 0))
            check(arm + ': ONE alias per complete owner and normalized81 hypotheses',
                  actual['aliases'].shape == (81, 2) and
                  set(map(tuple, actual['aliases'])) == {(a, b) for a in range(-4, 5) for b in range(-4, 5)})
            positions.append(actual['common_position_east_north_km'].copy())
            window = actual['window_s'].copy()
            noise_excess = actual['covariance_hz2'] - np.diag(2 * sigma ** 2)
            # Posterior radio/owner covariance is PSD; small eigen error is
            # judged at its floating-point matrix scale, not as an RF gate.
            tolerance = 100 * np.finfo(float).eps * max(1., np.linalg.norm(noise_excess, ord=2))
            check(arm + ': archived Gaussian background retains native2sigma2 noise floor',
                  np.linalg.eigvalsh(noise_excess).min() >= -tolerance)
        proposal = read(root / 'proposal.json'); pieces = np.array(proposal['pieces'])
        check(arm + ': common panel partition covers entire computational window without gap',
              len(pieces) <= 512 and np.all(pieces[:, 1] > pieces[:, 0]) and
              pieces[0, 0] == window[0] and pieces[-1, 1] == window[1] and
              np.array_equal(pieces[:-1, 1], pieces[1:, 0]) and
              proposal['remote_mass_renormalized'] is False and proposal['cuts'] == [14, 21, 29])
        dreplay = read(root / 'D_replay.json'); replay = read(root / 'replay.json')
        original_D = read(OLD / arm / 'D_evidence.json')['objective']
        original_poly = read(OLD / arm / 'CH4_mixed_evidence.json')['objective']
        check(arm + ': exact original discovery density and independentGL replay',
              dreplay['original_D_objective'] == original_D and dreplay['passed'] and
              abs(dreplay['window_objective64'] - original_D) <= 1e-3 and
              abs(dreplay['window_objective32'] - dreplay['window_objective64']) <= 1e-3)
        check(arm + ': whole-polynomial joint score replays original same-law control',
              replay['passed'] and not replay['parent_recalibrated'] and
              replay['whole_polynomial_old_objective'] == original_poly and
              replay['window_objective_error'] <= 1e-3)
        tail = read(root / 'remote_guard.json'); envelope = tail['D_tail_enclosure']
        ceiling = -.5 * (43 * np.log(2 * np.pi) + np.log(2 * sigma[57:] ** 2).sum())
        remote = envelope['upper_log_integral'] + ceiling
        check(arm + ': global remote upper uses all D aliases and original unrenormalized prior',
              envelope['all_physical_aliases_bounded'] and envelope['original_prior_normalization'] and
              envelope['panels'] <= 8192 and envelope['lower_log_integral'] <= envelope['upper_log_integral'] and
              tail['remote_not_renormalized'] and not tail['Gamma_mixture_ceiling_claimed'] and
              abs(tail['native_W_Gaussian_log_density_ceiling'] - ceiling) < 1e-10 and
              abs(tail['global_joint_remote_upper_log_evidence'] - remote) < 1e-10)
        max_gl = 0.; absolute = 0
        for row in result['models']:
            name = row['name']; b = row['bounds']
            quad = read(root / (name + '_quadrature.json'))
            primary = read(root / (name + '_primary.json'))
            bound = read(root / (name + '_bounds.json'))
            expected_gl = 2 * abs(row['log_integral32'] - row['log_integral64'])
            max_gl = max(max_gl, expected_gl); absolute += b['absolute_precision']
            check(arm + ': ' + name + ' checkpoint, independent quadrature and valid interval',
                  bound == row and primary['log_integral32'] == row['log_integral32'] and
                  all(quad[k] == v for k, v in row.items() if k != 'bounds') and
                  expected_gl == row['quadrature_difference_objective'] and expected_gl <= 1e-3 and
                  row['independent_quadrature_passed'] and b['resolved'] and b['panels'] <= 512 and
                  b['lower_log_integral'] <= row['log_integral64'] <= b['upper_log_integral'] and
                  abs(b['objective_width'] - 2 * (b['upper_log_integral'] - b['lower_log_integral'])) < 1e-9 and
                  b['absolute_precision'] == (b['objective_width'] <= 1e-3))
        rebuilt = []
        for family in ('whole_physical', 'whole_polynomial', 'split', 'piecewise_polynomial'):
            rows = [row for row in result['models'] if row['family'] == family]
            count = {'whole_physical': 1, 'whole_polynomial': 1, 'split': 6, 'piecewise_polynomial': 3}[family]
            saved = next(row for row in result['classes'] if row['family'] == family)
            lower = logsumexp([row['bounds']['lower_log_integral'] - np.log(count) for row in rows])
            upper_local = logsumexp([row['bounds']['upper_log_integral'] - np.log(count) for row in rows])
            upper = np.logaddexp(upper_local, remote)
            point = logsumexp([row['log_integral64'] - np.log(count) for row in rows])
            weights = {row['name']: float(np.exp(row['log_integral64'] - np.log(count) - point)) for row in rows}
            check(arm + ': normalized ' + family + ' class lower/upper and window mixture',
                  len(rows) == count and all(abs(row['log_within_prior'] + np.log(count)) < 1e-14 for row in rows) and
                  saved['normalized_cells'] == count and saved['class_prior'] == .25 and
                  max(abs(saved['lower_log_evidence'] - lower), abs(saved['upper_log_evidence'] - upper),
                      abs(saved['window_log_evidence'] - point), abs(saved['window_objective'] + 2 * point)) < 1e-9 and
                  abs(sum(weights.values()) - 1) < 1e-10 and
                  all(abs(saved['within_class_window_weights'][key] - value) < 1e-10 for key, value in weights.items()))
            rebuilt.append(dict(family=family, lower=float(lower), upper=float(upper),
                window_objective=float(-2 * point), conditional_window_objective=float(-2 * point - original_D)))
        split = next(row for row in rebuilt if row['family'] == 'split')
        margin = split['lower'] - max(row['upper'] for row in rebuilt if row['family'] != 'split')
        proof = result['ordering']
        check(arm + ': global class ordering independently rederived, without identity/precision claim',
              proof['proved'] and proof['winner'] == 'split' and margin > 0 and
              abs(proof['minimum_log_evidence_margin'] - margin) < 1e-10 and
              not proof['identity_assignment'] and not proof['portion_adoption'] and not proof['absolute_precision_implied'])
        metrics.append(dict(arm=arm, classes=rebuilt, minimum_global_log_evidence_margin=margin,
            all11_GL_passed=True, maximum_GL_objective_discrepancy=max_gl, absolute_precision_cells=absolute,
            D_replay_error=dreplay['error'], whole_polynomial_replay_error=replay['window_objective_error'],
            split_window_weights=next(row for row in result['classes'] if row['family'] == 'split')['within_class_window_weights'],
            remote_guard_stopped_for_exclusion=envelope['stopped_for_certified_exclusion']))
    check('both arms use exactly same saved c0 RF position', np.array_equal(*positions))
    check('earlier independent native ownership and exact duration audit still applies', read(HERE / 'ownership_check.json')['all_passed'])
    diff = subprocess.check_output(['git', 'diff', '--binary', '--no-ext-diff'], cwd='/home/mouse9911/gits/leo-tracker-reduxredux')
    check('unrelated tracked working-tree diff preserved', hashlib.sha256(diff).hexdigest() ==
          'add0a0f9598b5045dbf6dd6eb05b744b856715c01a9cb3101f6890b999029a4b')
    seconds = time.monotonic() - start
    cumulative_audit = seconds + read(HERE / 'preflight02.json')['cumulative_audit_seconds']
    receipt = dict(all_passed=all(row['passed'] for row in checks) and cumulative_audit <= 180,
        protocol_sha256=digest, RF_seal_sha256=sha(RUN / 'RF_seal.json'), source_sha256=sha(__file__),
        checks=checks, metrics=metrics, seconds=seconds, cumulative_audit_seconds=cumulative_audit,
        audit_cap_seconds=180, corpus_propagation_calls=0, new_RF_scores=0, position_fits=0, geographic_truth_read=False,
        interpretation='Normalized split class wins within declared conditional models with global analytic evidence bounds. No absolute1e-3 certification, authenticated identity, graph-switch proof, partial acceptance or position gain follows.')
    with (HERE / 'terminal.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(all_passed=receipt['all_passed'], checks=len(checks),
        failed=[row for row in checks if not row['passed']], metrics=metrics, seconds=seconds)))


if __name__ == '__main__':
    main()
