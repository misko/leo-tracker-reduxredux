"""Independent artifact-only checks; no propagation, optimization or geography."""
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
SCI = HERE.parent / 'scientific'
PERIOD = 1 / 4.4e-6
ARMS = ('c0', 'fitted_c')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output = HERE / 'terminal.json'
    if output.exists():
        raise FileExistsError('preserve audit receipts')
    began = time.monotonic()
    checks, summaries, source_diagnostics = [], [], []

    def check(name, passed, **details):
        checks.append(dict(name=name, passed=bool(passed), **details))

    protocol = read(SCI / 'protocol02.json')
    seal = read(SCI / 'RF_seal.json')
    bindings = dict(protocol['source_input_hashes'])
    bindings.update(seal['files'])
    bad = [p for p, expected in bindings.items() if sha(p) != expected]
    check('frozen protocol and every scientific/input binding unchanged',
          not bad and sha(SCI / 'protocol02.json') == seal['protocol_sha256'] == read(HERE / 'preflight.json')['protocol_sha256'],
          binding_count=len(bindings), mismatches=bad)
    source = Path('/srv/bulk/leo/research/ds25-20261024')
    tracks = {row['key']: row for row in read(source / 'DS24-0013/tracks.json')}
    observations = {row['observation_id']: row for row in read(source / 'DS24-0013/observations.json')}
    parent = read(source / 'family_cavity/position/DS24-0013.json')
    ownership = read('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership/DS24-0013/parent.json')['coverage']
    node = parent['selected']['node'] if parent['accepted'] else parent['baseline_node']
    identity_by_id = {}
    for row in node['seed']['rows']:
        for oid in tracks[row['component']]['observation_ids']:
            identity_by_id[oid] = row['candidate_index']
    entries = parent['selected']['entries'] if parent['accepted'] else parent['baseline_entries']
    for row in entries:
        for oid in row['observation_ids']:
            identity_by_id[oid] = row['candidate_index']
    original = {a: read(SCI / ('original_parent_' + a + '.json')) for a in ARMS}
    x = np.asarray(parent['baseline_arms']['c0']['endpoint_east_north_km'])
    for arm, info in original.items():
        ids = info['calibration_ids'] + info['predictive_ids']
        check('original accepted membership unchanged: ' + arm,
              len(ids) == len(set(ids)) == 3784 and set(ids) == set(ownership[arm]['accepted_observation_ids'])
              and set(ids) == set(info['original_accepted_IDs']) and not info['operational_membership_changed']
              and np.array_equal(info['common_position_east_north_km'], x))
    all_ids, candidate_count, absolute_count = [], 0, 0
    max_coarse_error = max_null_error = 0.
    for index, selected in enumerate(protocol['sources']):
        directory = SCI / ('owner' + str(index))
        metadata = read(directory / 'metadata.json')
        track = tracks[selected['component']]
        ids = selected['observation_ids']
        all_ids.extend(ids)
        with np.load(directory / 'observations.npz') as n:
            check('whole original source and native gauge: ' + metadata['owner'],
                  list(n['native_ids']) == ids == track['observation_ids'] and
                  np.array_equal(n['times_s'], track['times']) and np.array_equal(n['values_hz'], track['values']) and
                  np.max(abs(n['values_hz'] - np.array([observations[oid]['measured_cfo_hz'] for oid in ids]) + 2 * PERIOD)) < 1e-7
                  and np.allclose(n['q'], track['rf_hz'] / 11.5e9, rtol=0, atol=1e-15))
        cat = np.load(directory / 'catalogue.npz')
        pool = read(directory / 'c0_screen.json')['candidate_indices']
        pool_norads = list(map(int, cat['norads'][pool]))
        check('ordinary unforced exact pool matched across arms: ' + metadata['owner'],
              len(pool) == len(set(pool)) == 8 and pool == metadata['exact_candidate_indices'] and
              pool_norads == metadata['exact_candidate_norads'] and 60108 not in pool_norads)
        for arm in ARMS:
            screen = read(directory / (arm + '_screen.json'))
            with np.load(directory / (arm + '_nomination_background.npz')) as b:
                root = np.linalg.cholesky(b['covariance_hz2'])
                raw = b['raw_hz'][None, :] - cat['frequency_hz']
                alias = np.rint(-raw.mean(axis=1) / PERIOD).astype(int)
                residual = solve_triangular(root, (raw + alias[:, None] * PERIOD).T, lower=True)
                tangent = solve_triangular(root, (cat['derivative_hz_per_s'] * cat['phase_sd_s'][:, None]).T, lower=True)
                norm = np.sum(tangent ** 2, axis=0)
                coefficient = np.sum(residual * tangent, axis=0) / (1 + norm)
                # Independent positive-ridge representation of the rank-one density.
                costs = np.sum((residual - tangent * coefficient) ** 2, axis=0) + coefficient ** 2
                costs += np.log1p(norm) + 2 * np.log(np.diag(root)).sum() + len(ids) * np.log(2 * np.pi)
                visible = cat['minimum_mean_elevation_deg'] >= 0
                ranked = sorted(np.flatnonzero(visible), key=lambda j: (costs[j], int(cat['norads'][j])))
                saved_costs = np.array([np.nan if v is None else v for v in screen['coarse_scores']])
                coarse_error = float(np.max(abs(costs[visible] - saved_costs[visible])))
                max_coarse_error = max(max_coarse_error, coarse_error)
                check('full1487 ordinary screen independently reproduced: ' + metadata['owner'] + '/' + arm,
                      len(cat['norads']) == screen['catalogue_count'] == 1487 and
                      ranked == screen['ranked_visible_indices'] and ranked[:8] == screen['candidate_indices'] and
                      np.array_equal(np.asarray(screen['coarse_aliases'])[:, 0], alias) and
                      not screen['forced_or_reserved_candidate'] and coarse_error < 1e-6,
                      maximum_objective_error=coarse_error)
                j = int(np.flatnonzero(cat['norads'] == 57450)[0])
                phase_residual = raw[j] + alias[j] * PERIOD
                rms = float(np.sqrt(np.mean(phase_residual ** 2)))
                scatter = float(np.std(phase_residual))
            cavity = read(directory / (arm + '_cavity.json'))
            for name in ('calibration', 'predictive'):
                old_ids = original[arm][name + '_ids']
                expected = [oid for oid in old_ids if identity_by_id[oid] not in pool]
                removed = [oid for oid in old_ids if identity_by_id[oid] in pool]
                field = 'removed_curved_ids' if name == 'calibration' else 'removed_predictive_ids'
                check('symmetric family cavity exact ' + name + ' IDs: ' + metadata['owner'] + '/' + arm,
                      cavity[name + '_ids'] == expected and cavity[field] == removed)
            check('hard original fixed-context guards: ' + metadata['owner'] + '/' + arm,
                  cavity['phase_qualified'] and cavity['precision_qualified'] and cavity['support_qualified'] and
                  cavity['final_phase_change_s'] <= .01 and cavity['maximum_unclipped_parent_phase_s'] <= 15.000001 and
                  np.isfinite(cavity['final_log_precision_change']) and cavity['final_log_precision_change'] <= 1e-5 and
                  cavity['retained_calibration_nonempty'] and bool(cavity['retained_supported_families']))
            result = read(directory / (arm + '_result.json'))
            with np.load(directory / (arm + '_conditional.npz')) as c:
                check('shared exact data/covariance/aliases/common RF position: ' + metadata['owner'] + '/' + arm,
                      list(c['native_ids']) == ids and np.array_equal(c['values_hz'], track['values']) and
                      np.array_equal(c['times_s'], track['times']) and
                      np.array_equal(c['aliases'][:, 0], np.arange(-4, 5)) and
                      np.array_equal(c['common_position_east_north_km'], x) and
                      np.array_equal(result['common_position_east_north_km'], x) and
                      np.isfinite(c['parent_coefficients']).all() and np.isfinite(c['parent_noise']).all() and
                      np.linalg.eigvalsh(c['covariance_hz2']).min() > 0)
                # Independent complete observation-space Gaussian, not copied QR.
                z = 2 * (c['times_s'] - min(c['times_s'])) / np.ptp(c['times_s']) - 1
                poly = np.polynomial.legendre.legvander(z, 4) * PERIOD / np.sqrt(6)
                null_root = np.linalg.cholesky(c['covariance_hz2'] + poly @ poly.T)
                white = solve_triangular(null_root, (c['raw_hz'][None, :] + np.arange(-4, 5)[:, None] * PERIOD).T, lower=True)
                log_density = -.5 * (np.sum(white ** 2, axis=0) + 2 * np.log(np.diag(null_root)).sum() + len(ids) * np.log(2 * np.pi))
                null_objective = float(-2 * (logsumexp(log_density) - np.log(9)))
                null_error = abs(null_objective - result['null']['objective'])
                max_null_error = max(max_null_error, null_error)
                check('proper same-measure null independently replayed: ' + metadata['owner'] + '/' + arm,
                      null_error <= 1e-6 and result['null']['independent_dense_passed'] and
                      result['null']['independent_dense_error'] <= 1e-7, objective_error=null_error)
            check('all eight attempted candidate slots retained: ' + metadata['owner'] + '/' + arm,
                  result['status'] == 'complete' and [q['candidate_index'] for q in result['candidates']] == pool and
                  [q['norad'] for q in result['candidates']] == pool_norads and
                  all((directory / (arm + '_' + str(n) + '_checkpoint.json')).exists() for n in pool_norads))
            models = [('unresolved', None, -.5 * (result['null']['objective'] + 1e-6), -.5 * (result['null']['objective'] - 1e-6))]
            for row in result['candidates']:
                candidate_count += 1
                absolute_count += int(row['numerically_qualified'])
                support = read(directory / (arm + '_' + str(row['norad']) + '_support.json'))
                lower = row['full_support_lower_log_integral']
                upper = row['full_support_upper_log_integral']
                inner, roots = row['physical_enclosure'], row['root_enclosure']
                merged_upper = inner['upper_log_integral']
                if roots['upper_log_integral'] is not None:
                    merged_upper = float(np.logaddexp(merged_upper, roots['upper_log_integral'])) if merged_upper is not None else roots['upper_log_integral']
                check('support and conservative evidence bounds: ' + metadata['owner'] + '/' + arm + '/' + str(row['norad']),
                      support['certified'] and not support['unresolved_intervals'] and row['certified_visibility'] and
                      not row['visible_mass_renormalized'] and lower == inner['lower_log_integral'] and
                      upper == merged_upper and np.isfinite([lower, upper]).all() and lower <= upper and
                      inner['all_physical_aliases_bounded'] and inner['original_prior_normalization'] and
                      row['objective_distance_to_full_enclosure'] > 1e-3 and not row['numerically_qualified'])
                models.append(('physical', row['norad'], lower, upper))
            winners = [(kind, norad, lower - max(q[3] for q in models if q[:2] != (kind, norad)))
                       for kind, norad, lower, upper in models if lower > max(q[3] for q in models if q[:2] != (kind, norad))]
            order = result['evidence_order_certificate']
            check('strict complete finite-pool ordering independently replayed: ' + metadata['owner'] + '/' + arm,
                  len(winners) == 1 and order['proved'] and winners[0][:2] == (order['winner_kind'], order['winner_norad']) and
                  abs(winners[0][2] - order['minimum_log_evidence_margin']) < 1e-10 and
                  order['models_compared'] == 9 and not order['absolute_score_precision_implied'] and
                  not result['ordering_absolute_precision_qualified'])
            check('no acceptance/position or discovery-conditioned inference: ' + metadata['owner'] + '/' + arm,
                  not result['original_accepted_IDs_changed'] and not result['operational_identity_assignment'] and
                  not result['discovery_conditioned_evidence'] and result['position_fits'] == 0 and not result['GPS_used'])
            summaries.append(dict(owner=metadata['owner'], arm=arm, points=len(ids),
                ordinary_60108_rank=screen['ranked_visible_norads'].index(60108) + 1,
                raw_physical_winner=result['raw_physical_winner_norad'],
                physical_minus_null=result['physical_minus_null'], certified_winner_kind=order['winner_kind'],
                certified_winner_norad=order['winner_norad'], minimum_log_evidence_margin=order['minimum_log_evidence_margin'],
                original_remaining_gates_pass=cavity['original_remaining_gates_pass'],
                removed_curved_points=len(cavity['removed_curved_ids']), removed_predictive_points=len(cavity['removed_predictive_ids'])))
            if index == 1:
                source_diagnostics.append(dict(arm=arm, norad=57450, causal_mean_nomination_background_RMS_hz=rms,
                    causal_mean_nomination_background_centered_RMS_hz=scatter,
                    phase_prior_location_s=result['candidates'][0]['original_phase_location_s'],
                    phase_prior_SD_parameter_s=result['candidates'][0]['original_phase_sd_s'],
                    posterior_physical_adequacy_tested=False))
        cat.close()
    check('124 unique nonoverlapping native IDs and full6/48 denominator',
          len(all_ids) == len(set(all_ids)) == 124 and candidate_count == 48 and len(summaries) == 6 and
          all(not set(all_ids) & set(ownership[a]['accepted_observation_ids']) for a in ARMS))
    original_curved_57450 = [row for row in node['seed']['rows'] if row['candidate_norad'] == 57450 and
                            set(tracks[row['component']]['observation_ids']) & set(original['c0']['calibration_ids'])]
    original_predictive_57450 = [row for row in entries if row['candidate_index'] == 439]
    check('57450 has no existing accepted parent orbit evidence',
          not original_curved_57450 and not original_predictive_57450,
          curved_owners=0, curved_points=0, predictive_owners=0, predictive_points=0,
          rejected_graph_owners=[row['component'] for row in node['seed']['rows'] if row['candidate_norad'] == 57450])
    execution = read(SCI / 'execution.json')
    prep = read(SCI / 'preparation.json')['scientific_seconds']
    worker_seconds = sum(row['scientific_worker_seconds'] for row in execution['arms'])
    check('all terminal once within original scientific cap; no fits or GPS',
          execution['all_selected_terminal'] and execution['selected_sources'] == 3 and
          execution['selected_owner_arm_contexts'] == 6 and execution['selected_candidate_contexts'] == 48 and
          abs(execution['total_scientific_seconds'] - prep - worker_seconds) < 1e-9 and
          execution['total_scientific_seconds'] <= 600 and execution['position_fits'] == 0 and
          not execution['GPS_used'] and not execution['operational_identity_assignment'] and
          not execution['discovery_conditioned_evidence_executed'])
    check('all scientific bindings remain immutable at audit completion', all(sha(p) == h for p, h in bindings.items()))
    elapsed = time.monotonic() - began
    prior_seconds = read(HERE / 'preflight.json')['cumulative_audit_seconds']
    receipt = dict(all_passed=all(q['passed'] for q in checks), checks=checks,
        protocol_sha256=sha(SCI / 'protocol02.json'), RF_seal_sha256=sha(SCI / 'RF_seal.json'),
        source_sha256=sha(__file__), terminal_seconds=elapsed,
        cumulative_audit_seconds=prior_seconds + elapsed, audit_cap_seconds=180,
        maximum_coarse_positive_ridge_objective_discrepancy=max_coarse_error,
        maximum_independent_dense_null_objective_discrepancy=max_null_error,
        owner_arm_results=summaries, CH5_descriptive_diagnostics=source_diagnostics,
        candidate_contexts=candidate_count, candidate_absolute_precision_qualified=absolute_count,
        corpus_propagation_calls=0, position_fits=0, geographic_truth_read=False,
        interpretation='bounds certify only declared finite-pool conditional model ordering; not physical adequacy, calibrated identity or position improvement')
    receipt['all_passed'] &= receipt['cumulative_audit_seconds'] <= 180
    output.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(path=str(output), all_passed=receipt['all_passed'], checks=len(checks),
        cumulative_audit_seconds=receipt['cumulative_audit_seconds'], failed=[q for q in checks if not q['passed']])))


if __name__ == '__main__':
    main()
