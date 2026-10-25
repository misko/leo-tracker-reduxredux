"""Independent saved-result arithmetic; no propagation, fits or geography."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_text())


def main():
    paths = ['information/results.json', 'information/inventory.json',
             'audit/shape_support_inventory.json', 'nomination/summary.json']
    results, inventory, shape, nomination = [read(name) for name in paths]
    rows = results['rows']
    checks = {}
    checks['complete_source_inventory'] = len(rows) == 26
    checks['scored_and_blocked_retained'] = (
        sum(r['status'] == 'complete' for r in rows) == 25
        and sum(r['status'] != 'complete' for r in rows) == 1)
    expected = {'DS24-0010': (64023, 59333), 'DS24-0011': (65497, 58175),
                'DS24-0012': (57743, 62145), 'DS24-0013': (60108, 60108)}
    for case, winners in expected.items():
        actual = tuple(next(r['candidate_norad'] for r in rows
                            if r['case'] == case and r.get(key) == 1)
                       for key in ('count_rank', 'information_rank'))
        checks[case + '_winners'] = actual == winners
    for row in rows:
        if row['status'] == 'complete':
            values = [a['fractional_weak_variance_reduction']
                      for a in row['arms'].values()]
            checks[row['component'] + '_paired_score'] = (
                row['paired_ranking_score'] == min(values))
    missing = [r for r in shape['families'] if not r['physical_mode_prior_present']]
    curved = sum(len(r['curved_ids']) for r in missing)
    predictive = sum(len(r['predictive_ids']) for r in missing)
    denominator = sum(c['original_likelihood_counts']['c0'] for c in inventory['cases'])
    checks['missing_shape_counts'] = (
        len(shape['families']) == 89 and len(missing) == 33
        and (curved, predictive, denominator) == (1147, 397, 12442))
    for row in nomination['summaries']:
        key = row['arm'] + '_' + row['kind']
        if row['kind'] == 'physical':
            checks[key] = all(row[k] == v for k, v in
                [('selected', 8), ('complete', 8), ('truth_in_shortlist', 8),
                 ('raw_best_physical_is_truth', 8), ('numerically_qualified', 7)])
        else:
            checks[key] = all(row[k] == v for k, v in
                [('selected', 4), ('complete', 4),
                 ('raw_unresolved_density_preference', 4), ('numerically_qualified', 0)])
    output = dict(all_passed=all(checks.values()), checks=checks,
                  missing_shape_point_fraction=(curved + predictive) / denominator,
                  fits=0, propagation_calls=0, GPS_read=False,
                  input_sha256={p: hashlib.sha256((HERE / p).read_bytes()).hexdigest()
                                for p in paths})
    path = HERE / 'coordinator_checks.json'
    with path.open('x') as stream:
        json.dump(output, stream, indent=2)
    print(json.dumps(dict(all_passed=output['all_passed'], checks=len(checks),
                          missing_shape_point_fraction=output['missing_shape_point_fraction'])))
    if not output['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
