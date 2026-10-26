"""Independent pool/ownership and shared-nuisance information preflight."""
import hashlib
import inspect
import json
from pathlib import Path
import signal
import sys
import time

import numpy as np
import pytest
from scipy.linalg import solve_triangular

HERE = Path(__file__).resolve().parent
INV = HERE.parent / 'inventory'
sys.path.insert(0, str(INV))
import expand as e

read = lambda path: json.loads(Path(path).read_bytes())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def information(j, u, weights, prior):
    whitened_j = j * np.sqrt(weights[:, None])
    augmented_u = np.vstack((u * np.sqrt(weights[:, None]), np.diag(np.sqrt(prior))))
    augmented_j = np.vstack((whitened_j, np.zeros((len(prior), j.shape[1]))))
    q = np.linalg.qr(augmented_u, mode='reduced')[0]
    residual = augmented_j - q @ (q.T @ augmented_j)
    return residual.T @ residual


def main():
    start = time.monotonic(); checks = []
    def check(name, passed, **detail):
        checks.append(dict(name=name, passed=bool(passed), **detail))
    protocol = read(INV / 'protocol.json'); digest = sha(INV / 'protocol.json')
    metadata = read(INV / 'metadata.json'); inventory = read(INV / 'inventory.json')
    check('exact frozen source/input and nested cohort/exposure bindings',
          digest == 'd559bca7752cfe71e546bacf9ab0b44d7ee0c502f02959abe9829ec5e088f371' and
          all(sha(path) == value for path, value in protocol['source_and_input_bindings'].items()) and
          all(path in protocol['source_and_input_bindings'] and sha(path) == value for path, value in metadata['bindings'].items()),
          bindings=len(protocol['source_and_input_bindings']))
    cohort = sorted([row for row in read(e.L.COHORT)['rows'] if row['eligible']], key=lambda row: (row['captured_utc_ns'], row['case']))
    expected = [row['case'] for row in cohort]
    check('exact24-case chronology, no case substitution and fixed5percent/four-case rule',
          len(expected) == 24 and expected == inventory['selection_case_order'] == protocol['cases'] and
          protocol['minimum_fractional_weak_variance_reduction_each_arm'] == .05 and
          protocol['maximum_distinct_new_case_nominees'] == 4 and protocol['new_choice_excluded_cases'] == list(e.L.OLD_FOUR))
    rows_by_case = {case: [row for row in inventory['sources'] if row['case'] == case] for case in expected}
    for case in expected:
        case_meta = next(row for row in inventory['cases'] if row['case'] == case)
        packet = read(case_meta['ownership_receipt']); coverage = packet['coverage']
        parent_path = e.L.SOURCE / 'family_cavity/position' / (case + '.json')
        track_path = e.L.SOURCE / case / 'tracks.json'
        check(case + ': full ownership receipt matches original parent/track/native-observation bytes',
              case_meta['ownership_status'] == 'complete' and packet['source_parent_sha256'] == sha(parent_path) and
              packet['source_tracks_sha256'] == sha(track_path) and
              packet['source_observations_sha256'] == sha(e.L.SOURCE / case / 'observations.json'))
        tracks = read(track_path); parent = read(parent_path)
        node = parent['selected']['node'] if parent['accepted'] else parent['baseline_node']
        canonical = {row['component']: (index, row, alias) for index, (row, alias) in
                     enumerate(zip(node['seed']['rows'], node['aliases'], strict=True))}
        case_rows = rows_by_case[case]
        ids = [oid for track in tracks for oid in track['observation_ids']]
        check(case + ': every complete native owner retained with exact order/IDs and no duplication',
              len(case_rows) == len(tracks) and len(ids) == len(set(ids)) and
              all(row['component'] == tracks[row['track_index']]['key'] and
                  row['observation_ids'] == tracks[row['track_index']]['observation_ids'] for row in case_rows))
        for arm in e.L.ARMS:
            role = coverage[arm]
            check(case + '/' + arm + ': accepted union includes curved/predictive/postfit without loss',
                  set(role['accepted_observation_ids']) == set(role['curved_observation_ids']) |
                  set(role['predictive_observation_ids']) | set(role['postfit_only_observation_ids']))
        for row in case_rows:
            if row['eligible']:
                index, original, alias = canonical[row['component']]
                valid = (original['active_curvature'] and row['row_index'] == index and row['alias'] == alias and
                    row['candidate_index'] == original['candidate_index'] and
                    all(not set(row['observation_ids']) & set(coverage[arm]['accepted_observation_ids']) for arm in e.L.ARMS))
                check(case + '/' + row['component'] + ': eligible whole source has original curved binding and both-arm nonoverlap', valid)
    preparation = read(INV / 'preparation.json')
    check('real parent-design smoke, full24 ownership and exact old-four reuse prerequisites pass',
          preparation['complete_ownership_cases'] == 24 and preparation['eligible_sources'] == 148 and
          preparation['old_four_reuse_all_bindings_unchanged'] and
          all(abs(v['parent_objective_difference']) < 1e-3 and np.isfinite(v['Gamma_change']) and v['Gamma_change'] <= 1e-5
              for v in preparation['smoke']['arms'].values()) and
          not (INV / 'results.json').exists())
    check('original scientific functions reused unchanged; cap and no-position/GPS scope frozen',
          all(Path(fun.__code__.co_filename) == e.L.OLD / 'ranking.py' for fun in
              (e.K.parent_design, e.K.target_design, e.K.gain, e.K.redacted_target)) and
          protocol['maximum_cumulative_worker_seconds'] == 600 and protocol['workers'] <= 2 and
          protocol['BLAS_threads'] == 1 and protocol['no_position_fits'] and protocol['no_GPS_or_errors'] and
          protocol['no_new_nomination'])
    status = pytest.main(['-q', '-p', 'no:cacheprovider', str(INV / 'test_expand.py')])
    signal.setitimer(signal.ITIMER_REAL, 0)
    check('four owned pool/selection/partial-arm controls independently rerun', status == 0)
    rng = np.random.default_rng(202610260712)
    j = rng.normal(size=(17, 2)); u = rng.normal(size=(17, 5)); weights = rng.uniform(.4, 2., 17); prior = rng.uniform(.7, 2., 5)
    jt = rng.normal(size=(8, 2)); ht = rng.normal(size=(8, 5)); extra = rng.normal(size=(8, 4)); variance = rng.uniform(1., 4., 8)
    gram = np.diag(prior) + u.T @ (weights[:, None] * u)
    root = np.linalg.cholesky(gram); response = np.linalg.solve(gram, u.T @ (weights[:, None] * j))
    gain, conditional, effective = e.K.gain(jt, ht, variance, extra, root, response)
    base = information(j, u, weights, prior)
    augmented = information(np.vstack((j, jt)), np.vstack((np.column_stack((u, np.zeros((17, 4)))),
        np.column_stack((ht, extra)))), np.r_[weights, 1 / variance], np.r_[prior, np.ones(4)])
    error = float(np.max(abs(base + gain - augmented)))
    check('independent joint augmented-QR agrees with shared-nuisance conditional Schur information',
          error < 1e-10 and np.linalg.eigvalsh(gain).min() >= -1e-12, maximum_information_error=error)
    check('source/inputs immutable after independent checks',
          all(sha(path) == value for path, value in protocol['source_and_input_bindings'].items()))
    seconds = time.monotonic() - start
    result = dict(all_passed=all(row['passed'] for row in checks) and seconds <= 180,
        protocol_sha256=digest, checks=checks, seconds=seconds, source_sha256=sha(__file__),
        audit_numeric_cap_seconds=180, new_orbit_propagation_calls=0, new_target_ranks=0,
        position_fits=0, geographic_truth_read=False,
        scope='Local Gaussian mean-design information conditional on archived identities; no calibrated source/position probabilities or accuracy prediction.')
    with (HERE / 'inventory_preflight.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(all_passed=result['all_passed'], protocol_sha256=digest, seconds=seconds,
        checks=len(checks), failed=[row for row in checks if not row['passed']])))


if __name__ == '__main__':
    main()
