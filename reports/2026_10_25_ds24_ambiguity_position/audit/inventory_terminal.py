"""Artifact-only independent replay of ownership, information and allocation."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.linalg import solve_triangular

ROOT = Path(__file__).resolve().parent.parent
INV = ROOT / 'inventory'
read = lambda path: json.loads(Path(path).read_bytes())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def arrays(path):
    with np.load(path, allow_pickle=False) as data:
        return {name: data[name] for name in data.files}


def main():
    start = time.monotonic(); checks = []; maxima = Counter()
    def check(name, passed, **detail):
        checks.append(dict(name=name, passed=bool(passed), **detail))
    def close(a, b, key, rtol=1e-7, atol=1e-8):
        a, b = np.asarray(a), np.asarray(b)
        maxima[key] = max(maxima[key], float(np.max(np.abs(a-b))))
        return np.allclose(a, b, rtol=rtol, atol=atol)
    protocol = read(INV / 'protocol.json'); seal = read(INV / 'RF_seal.json')
    inv = read(INV / 'inventory.json'); result = read(INV / 'results.json')
    check('RF seal and all frozen input/source bindings exact',
        sha(INV / 'protocol.json') == result['protocol_sha256'] ==
        'd559bca7752cfe71e546bacf9ab0b44d7ee0c502f02959abe9829ec5e088f371' and
        all(sha(path) == value for path, value in seal['files'].items()) and
        all(sha(path) == value for path, value in protocol['source_and_input_bindings'].items()))
    source = {(q['case'], q['component']): q for q in inv['sources']}
    rows = {(q['case'], q['component']): q for q in result['rows']}
    check('all3265 complete-owner metadata rows preserved without substitution',
        len(source) == len(rows) == 3265 and source.keys() == rows.keys() and
        all(all(rows[key][k] == v for k, v in q.items()) for key, q in source.items()))
    for case in inv['selection_case_order']:
        meta = next(q for q in inv['cases'] if q['case'] == case)
        coverage = read(meta['ownership_receipt'])['coverage']
        pool = [q for q in result['rows'] if q['case'] == case]
        ids = [oid for q in pool for oid in q['observation_ids']]
        check(case + ': whole native IDs unique; eligible sources outside both full accepted unions',
            len(ids) == len(set(ids)) and all(not set(q['observation_ids']) & set(coverage[arm]['accepted_observation_ids'])
                for q in pool if q['eligible'] for arm in ['c0', 'fitted_c']))
    old = read(protocol['old_four_results']); oldrows = {(q['case'], q['component']): q for q in old['rows']}
    check('old-four exact numerical reuse and no repeated/rerolled outcomes',
        all(all(q[k] == oldrows[key][k] for k in ['status', 'arms'] + (['paired_ranking_score'] if q['status'] == 'complete' else []))
            for key, q in rows.items() if q.get('reused_original_information')))
    parent = {}
    for q in result['parents']:
        name = q['case'] + '/' + q['arm']; a = arrays(q['array_path']); parent[q['case'], q['arm']] = (q, a)
        response = np.linalg.solve(a['gram'], a['cross'])
        residual = a['position_design'] - a['nuisance_design'] @ response
        # Positive augmented-residual form avoids subtraction of two large precisions.
        info = residual.T @ (a['weights'][:, None] * residual) + response.T @ (a['prior'][:, None] * response)
        check(name + ': independent parent nuisance elimination, precision root and saved endpoint',
            sha(q['array_path']) == q['array_sha256'] and
            close(a['root'] @ a['root'].T, a['gram'], 'parent_root', rtol=1e-10, atol=1e-7) and
            close(response, a['response'], 'parent_response') and close(info, a['information'], 'parent_information') and
            close(info, q['information'], 'parent_record_information') and
            abs(q['parent_objective_difference']) < 1e-3 and np.isfinite(q['final_log_precision_change']) and
            q['final_log_precision_change'] <= 1e-5 and np.linalg.eigvalsh(info).min() > 0)
    check('all24 matched parent contexts present exactly once', len(parent) == 48)
    for key, q in rows.items():
        if q['status'] != 'complete':
            continue
        for arm in ['c0', 'fitted_c']:
            rec = q['arms'][arm]; pr, b = parent[q['case'], arm]; a = arrays(rec['array_path'])
            shared = solve_triangular(b['root'], a['h'].T, lower=True).T
            covariance = np.diag(a['noise_variance']) + shared @ shared.T + a['extra'] @ a['extra'].T
            effective = a['j'] - a['h'] @ b['response']
            root = np.linalg.cholesky(covariance)
            whitened = solve_triangular(root, effective, lower=True)
            gain = whitened.T @ whitened; information = b['information'] + gain
            weak = b['weak']; basevar = float(weak @ np.linalg.solve(b['information'], weak))
            variance = float(weak @ np.linalg.solve(information, weak)); fraction = 1 - variance/basevar
            roles = pr['role_map']; allowed = set(roles['hardware'] + roles['receiver_smooth'])
            if q['family_has_parent_likelihood']:
                label = str(q['candidate_norad'])
                allowed.add(roles['phase'][label]); allowed.update(roles['physical_modes'][label])
            forbidden = sorted(set(range(a['h'].shape[1])) - allowed)
            layout = (not forbidden or np.count_nonzero(a['h'][:, forbidden]) == 0)
            layout &= a['extra'].shape[1] == (1 if q['family_has_parent_likelihood'] else 5)
            layout &= np.all(a['extra'][:, -1] == 300.)
            check(q['component'] + '/' + arm + ': shared-covariance Schur, no dormant duplication and CFO-free design',
                sha(rec['array_path']) == rec['array_sha256'] and layout and
                close(covariance, a['conditional_covariance'], 'target_covariance', rtol=1e-10, atol=1e-7) and
                close(effective, a['effective_j'], 'target_effective_mean') and
                close(gain, a['information_gain'], 'target_information') and
                close(gain, rec['information_gain'], 'target_record_information') and
                close(information, rec['augmented_information'], 'augmented_information') and
                abs(fraction - rec['fractional_weak_variance_reduction']) < 1e-8 and
                abs(variance - rec['augmented_baseline_weak_variance_km2']) < 1e-8 and
                rec['target_CFO_redaction_maximum_difference'] == 0 and np.linalg.eigvalsh(gain).min() >= -1e-9)
        check(q['component'] + ': paired score is minimum of both unchanged c arms',
            q['paired_ranking_score'] == min(q['arms'][a]['fractional_weak_variance_reduction'] for a in ['c0', 'fitted_c']))
    # Independent full-pool and scoped-pool rank reconstruction, retaining blocked length winners.
    for case in inv['selection_case_order']:
        pool = [q for q in rows.values() if q['case'] == case and q['eligible']]
        for scoped in [False, True]:
            p = [q for q in pool if not scoped or q['unexhausted_within_declared_audit']]
            prefix = 'unexhausted_' if scoped else ''
            for field, order in [('count_rank', lambda q: (-q['points'], -q['span_s'], q['component'])),
                ('duration_rank', lambda q: (-q['span_s'], -q['points'], q['component'])),
                ('information_rank', lambda q: (-q['paired_ranking_score'], -q['points'], -q['span_s'], q['component']))]:
                eligible = [q for q in p if field != 'information_rank' or q['status'] == 'complete']
                check(case + ': ' + prefix + field + ' exact same-pool ordering',
                    all(q[prefix + field] == i for i, q in enumerate(sorted(eligible, key=order), 1)))
    selected = []
    for case in inv['selection_case_order']:
        if case in protocol['new_choice_excluded_cases']:
            continue
        pool = [q for q in rows.values() if q['case'] == case and q['eligible'] and q['status'] == 'complete' and
            q['unexhausted_within_declared_audit'] and all(q['arms'][a]['fractional_weak_variance_reduction'] >= .05 for a in ['c0', 'fitted_c'])]
        if pool:
            selected.append(min(pool, key=lambda q: (-q['paired_ranking_score'], -q['points'], -q['span_s'], q['component'])))
        if len(selected) == 4:
            break
    check('firstfour chronological >=5percent both-arm sources, no backfill/identity qualification',
        [q['component'] for q in selected] == [q['component'] for q in result['selection']] and
        [q['candidate_norad'] for q in selected] == [59733, 68904, 59786, 100180] and
        [q['archived_nomination_compatible'] for q in selected] == [False, False, True, False] and
        all(not q['identity_qualified'] and not q['family_has_parent_likelihood'] for q in selected))
    statuses = Counter(q['status'] for q in rows.values())
    remaining = [q for q in rows.values() if q['status'] == 'complete' and q['unexhausted_within_declared_audit'] and
        q['case'] not in protocol['new_choice_excluded_cases']]
    material = [q for q in remaining if q['paired_ranking_score'] >= .05]
    blocks = [q for q in rows.values() if q['status'] == 'blocked']
    check('all denominators, explicit original mode blocks and cumulative no-fit scope',
        statuses == Counter(excluded=3117, complete=146, blocked=2) and len(remaining) == 115 and
        len(material) == 24 and len({q['case'] for q in material}) == 12 and
        {(q['case'], q['candidate_norad']) for q in blocks} == {('DS24-0010', 69148), ('DS24-0015', 68267)} and
        all(q['incumbent_mode_block'] and all(a['status'] == 'blocked' for a in q['arms'].values()) for q in blocks) and
        not result['case_failures'] and result['cumulative_worker_seconds'] <= 600 and
        result['no_new_position_fits'] and result['no_GPS_or_errors'] and not result['identity_qualification'])
    seconds = time.monotonic() - start
    receipt = dict(all_passed=all(q['passed'] for q in checks), checks=checks, seconds=seconds,
        protocol_sha256=sha(INV / 'protocol.json'), RF_seal_sha256=sha(INV / 'RF_seal.json'),
        source_sha256=sha(__file__), maximum_absolute_replay_differences=dict(maxima), statuses=dict(statuses),
        selected=[dict(case=q['case'], norad=q['candidate_norad'], minimum_paired_gain=q['paired_ranking_score'],
            archived_compatible=q['archived_nomination_compatible']) for q in selected],
        orbit_propagation_calls=0, new_position_fits=0, geographic_truth_read=False,
        scope='Conditional local information only; three selected canonical nominations remain archived incompatible.')
    with (ROOT / 'audit/inventory_terminal.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(all_passed=receipt['all_passed'], checks=len(checks), seconds=seconds,
        failed=[q for q in checks if not q['passed']], maxima=dict(maxima))))


if __name__ == '__main__':
    main()
