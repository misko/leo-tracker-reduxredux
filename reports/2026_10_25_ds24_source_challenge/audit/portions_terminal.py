"""Independent saved-ranking, affine-density and native-coordinate audit."""
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.linalg import solve_triangular

HERE = Path(__file__).resolve().parent
PORT = HERE.parent / 'portions'
sys.path.insert(0, str(PORT))
import nominate as n

read = lambda path: json.loads(Path(path).read_bytes())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    start = time.monotonic(); checks = []; summaries = []; dense_errors = []
    def check(name, passed, **detail):
        checks.append(dict(name=name, passed=bool(passed), **detail))
    protocol = read(PORT / 'protocol.json'); seal = read(PORT / 'RF_seal.json')
    check('exact protocol/preflight/source/inputs and all RF-sealed outputs',
          sha(PORT / 'protocol.json') == seal['protocol_sha256'] == read(HERE / 'preflight.json')['protocol_sha256'] and
          read(HERE / 'preflight.json')['all_passed'] and
          all(sha(path) == h for path, h in protocol['source_input_hashes'].items()) and
          all(sha(path) == h for path, h in seal['files'].items()))
    execution = read(PORT / 'execution.json')
    seconds_sum = protocol['preparation_numeric_seconds'] + sum(row['scientific_numeric_seconds'] for row in execution['arms'])
    check('all14 selected contexts terminal with original180s cumulative budget',
          execution['all14_terminal'] and len(execution['arms']) == 2 and
          execution['cumulative_numeric_seconds'] == seconds_sum <= 180 and
          all(len(row['contexts']) == 7 and all(context['status'] == 'complete' for context in row['contexts']) for row in execution['arms']) and
          execution['position_fits'] == 0 and not execution['GPS_used'] and not execution['accepted'],
          cumulative_scientific_seconds=seconds_sum)
    catalogue = n.arrays(PORT / 'inputs/catalogue.npz')
    reference = int(np.flatnonzero(catalogue['norads'] == 57450)[0])
    for arm in ('c0', 'fitted_c'):
        obs = n.arrays(PORT / 'inputs' / (arm + '.npz'))
        for name, use in n.selections():
            result = read(PORT / arm / (name + '_screen.json'))
            cat = n.select_catalogue(catalogue, use)
            scores = np.array([np.inf if value is None else value for value in result['coarse_scores']])
            ranked = sorted(np.flatnonzero(np.isfinite(scores)), key=lambda j: (float(scores[j]), int(catalogue['norads'][j])))
            visible = cat['minimum_mean_elevation_deg'] >= 0
            check(arm + '/' + name + ': original complete catalogue sorted without reserve/backfill',
                  len(scores) == 1487 and np.array_equal(result['catalogue_norads'], catalogue['norads']) and
                  ranked == result['ranked_visible_indices'] and ranked[:8] == result['candidate_indices'] and
                  result['candidate_norads'] == catalogue['norads'][ranked[:8]].tolist() and
                  np.array_equal(np.isfinite(scores), visible) and not result['forced_or_reserved_candidate'])
            check(arm + '/' + name + ': native IDs and unchanged duration/curvature eligibility',
                  np.array_equal(result['native_IDs'], obs['native_ids'][use]) and
                  result['original_eligibility'] == n.eligibility(obs['times_s'][use], obs['graph_values_hz'][use]) and
                  not result['accepted'] and not result['exact_evidence'] and not result['background_response_selected_after_screen'])
            aliases = np.asarray(result['coarse_aliases'])[:, 0]
            z = np.array(result['phase_z'])
            means = catalogue['phase_means_s'] + catalogue['phase_sd_s'] * z
            check(arm + '/' + name + ': affine phase and unrestricted aliases reported without clipping',
                  np.allclose(means, result['linear_phase_mean_s'], atol=1e-12, rtol=0) and
                  np.array_equal(abs(means) <= 15, result['phase_mean_in_operational_domain']) and
                  np.array_equal(abs(aliases) <= 4, result['nearest_alias_in_finite_exact_support']))
            top = np.asarray(result['candidate_indices'])
            overlay = n.arrays(PORT / arm / (name + '_overlay.npz'))
            linear = cat['frequency_hz'][top] + cat['derivative_hz_per_s'][top] * (cat['phase_sd_s'][top] * z[top])[:, None]
            prediction = linear + obs['radio_mean_hz'][use] - aliases[top, None] * n.k.PERIOD + 2 * n.k.PERIOD
            check(arm + '/' + name + ': every affine overlay returns to same native CFO branch',
                  np.array_equal(overlay['native_ids'], obs['native_ids'][use]) and
                  np.array_equal(overlay['times_s'], obs['times_s'][use]) and
                  np.array_equal(overlay['norads'], catalogue['norads'][top]) and
                  np.allclose(prediction, overlay['predicted_affine_native_CFO_Hz'], atol=1e-9, rtol=0) and
                  np.allclose(obs['native_values_hz'][use] - prediction, overlay['residual_Hz'], atol=1e-9, rtol=0))
            # Verify saved nominees, not a new catalogue search or selection.
            for j in top:
                feature = cat['derivative_hz_per_s'][j] * cat['phase_sd_s'][j]
                covariance = obs['covariance_hz2'][np.ix_(use, use)] + np.outer(feature, feature)
                root = np.linalg.cholesky(covariance)
                raw = obs['raw_hz'][use] + aliases[j] * n.k.PERIOD - cat['frequency_hz'][j]
                white = solve_triangular(root, raw, lower=True)
                expected = white @ white + 2 * np.log(np.diag(root)).sum() + len(use) * np.log(2 * np.pi)
                error = abs(expected - scores[j]); dense_errors.append(error)
                check(arm + '/' + name + ': saved nominee ' + str(catalogue['norads'][j]) + ' dense Gaussian density',
                      error <= 1e-6 + 1e-10 * abs(expected), absolute_objective_error=error)
            summaries.append(dict(arm=arm, source=name, points=len(use), top8=result['candidate_norads'],
                diagnostic57450_rank=(ranked.index(reference) + 1) if reference in ranked else None,
                diagnostic57450_score=float(scores[reference]) if np.isfinite(scores[reference]) else None,
                top1_phase_mean_s=float(means[top[0]]), top1_alias=int(aliases[top[0]]),
                top1_phase_in_domain=bool(abs(means[top[0]]) <= 15),
                original_eligibility=result['original_eligibility']))
        for cut in (14, 21, 29):
            prefix = read(PORT / arm / ('cut' + str(cut) + '_prefix_screen.json'))['native_IDs']
            suffix = read(PORT / arm / ('cut' + str(cut) + '_suffix_screen.json'))['native_IDs']
            check(arm + ': cut' + str(cut) + ' partitions exactly all43 IDs without loss or duplication',
                  not set(prefix) & set(suffix) and prefix + suffix == obs['native_ids'].tolist())
    seconds = time.monotonic() - start
    cumulative = seconds + read(HERE / 'preflight.json')['seconds']
    receipt = dict(all_passed=all(row['passed'] for row in checks) and cumulative <= 180,
        checks=checks, rows=summaries, protocol_sha256=sha(PORT / 'protocol.json'), RF_seal_sha256=sha(PORT / 'RF_seal.json'),
        source_sha256=sha(__file__), seconds=seconds, cumulative_audit_seconds=cumulative,
        maximum_dense_saved_nominee_objective_error=max(dense_errors), saved_density_replays=len(dense_errors),
        new_catalogue_searches=0, propagation_calls=0, position_fits=0, geographic_truth_read=False,
        scope='Conditional ordinary proposal rankings and affine overlays only. Overlapping portions are not independent factors; no exact model comparison, source identity or partial adoption.')
    with (HERE / 'portions_terminal.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(all_passed=receipt['all_passed'], checks=len(checks), seconds=seconds,
        max_dense_error=max(dense_errors), failed=[row for row in checks if not row['passed']], rows=summaries)))


if __name__ == '__main__':
    main()
