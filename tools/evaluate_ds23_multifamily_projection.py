"""Independent RF replay, then report-only geography for the projection policy."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from algo02_scan import pair_passes
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_multifamily_proposals import score_position
from evaluate_ds23_multifamily_proposals import stats
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import summary
from probe_ds23_multifamily_projection import OUT, SOURCE, ARMS, prepare
from run_algo01_ds23_sample import read, write, sha


def verify_case(case):
    path, base_path = OUT / (case + '.json'), SOURCE / (case + '.json')
    record, base = read(path), read(base_path)
    if record['base_fit_sha256'] != sha(base_path):
        raise ValueError('base proposal source changed')
    attempted = bool(base['selected_full_arms'] and not base['accepted'])
    if attempted != record['attempted']:
        raise ValueError('projection attempted under a different rule')
    checks = []
    if attempted:
        scan, node, keep, _, _, signed, _, model, powers, means, entries = setup(case)
        if signed['policy_arms'] != base['incumbent_arms']:
            raise ValueError('published incumbent changed')
        for arm in ARMS:
            saved = record['projected_arms'][arm]
            x = np.asarray(saved['endpoint_east_north_km'])
            p = make_event_problem(scan, node, keep, arm, np.asarray(saved['phase_reference']), powers, means, model, [])
            attach_event_predictive(p, entries, powers)
            fresh = summary(p, x, entries)
            delta = fresh['negative_twice_elbo'] - saved['negative_twice_elbo']
            if abs(delta) > 1e-3:
                raise ValueError('projected full original-data RF endpoint changed')
            actual = [g['compatible'] for g in fresh['gates']['tracks'] + fresh['linear_gates']]
            expected = [g['compatible'] for g in saved['gates']['tracks'] + saved['linear_gates']]
            if actual != expected:
                raise ValueError('projected original gates changed')
            if np.max(abs(x)) > 12.5 + 1e-8:
                raise ValueError('projected point outside regional box')
            if record['projected_scores']:
                score = score_position(scan, node, keep, arm, powers, means, model, x)
                difference = score['score'] - record['projected_scores'][arm]['score']
                if abs(difference) > 1e-6:
                    raise ValueError('projected full cross-family score changed')
            else:
                difference = None
            checks.append(dict(arm=arm, RF_difference=delta, score_difference=difference))
    accepted = bool(attempted and pair_passes(record['projected_arms'], include_linear=True) and
        record['projected_scores'] and all(s['qualified'] for s in record['projected_scores'].values()) and
        all(g > 2*np.log(7) for g in record['score_gains'].values()))
    if accepted != record['accepted']:
        raise ValueError('projection policy changed')
    if record['policy_arms'] != (record['projected_arms'] if accepted else base['policy_arms']):
        raise ValueError('projection policy or fallback is not exact')
    return dict(case=case, fit_sha256=sha(path), base_fit_sha256=sha(base_path), checks=checks,
        accepted=accepted, no_GPS_read=True)


def verify():
    protocol = prepare()
    execution, base_check = read(OUT / 'execution.json'), read(SOURCE / 'verification_all.json')
    if not execution['all_terminal'] or execution['errors'] or not base_check['qualified']:
        raise ValueError('projection jobs and base RF verification must finish first')
    cases = protocol['development_cases'] + protocol['confirmation_cases']
    receipts, errors = [], []
    with ProcessPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(verify_case, c): c for c in cases}
        for future in as_completed(futures):
            try:
                receipts.append(future.result())
            except Exception as exc:
                errors.append(dict(case=futures[future], error=repr(exc)))
            write(OUT / 'verification_progress.json', dict(completed=len(receipts)+len(errors), total=len(cases)))
    write(OUT / 'verification.json', dict(all_terminal=True, qualified=not errors and len(receipts)==40,
        receipts=receipts, errors=errors, no_GPS_read=True,
        base_verification_sha256=sha(SOURCE / 'verification_all.json')))
    print('Verified', len(receipts), 'errors', errors, flush=True)


def evaluate():
    protocol = prepare()
    validation = read(OUT / 'verification.json')
    if not validation['qualified']:
        raise ValueError('all RF replays must qualify before geographic evaluation')
    bindings = {r['case']: r for r in validation['receipts']}
    from report_algo02_ds23 import position_error
    rows, results = [], {}
    figure, axes = plt.subplots(2, 2, figsize=(13, 9))
    for row, cohort in enumerate(('development', 'confirmation')):
        results[cohort] = {}
        for col, arm in enumerate(ARMS):
            results[cohort][arm] = {}
            values = {'incumbent': [], 'unprojected': [], 'projected': []}
            for case in protocol[cohort + '_cases']:
                path, base_path = OUT / (case + '.json'), SOURCE / (case + '.json')
                if sha(path) != bindings[case]['fit_sha256'] or sha(base_path) != bindings[case]['base_fit_sha256']:
                    raise ValueError('verified result changed')
                r, base = read(path), read(base_path)
                for kind, endpoint in (('incumbent', base['incumbent_arms'][arm]),
                        ('unprojected', base['policy_arms'][arm]), ('projected', r['policy_arms'][arm])):
                    values[kind].append(position_error(endpoint['endpoint_latlon']))
                rows.append(dict(case=case, cohort=cohort, arm=arm,
                    incumbent_error_km=values['incumbent'][-1], unprojected_error_km=values['unprojected'][-1],
                    projected_error_km=values['projected'][-1], projection_attempted=r['attempted'],
                    projection_accepted=r['accepted'], base_proposal_accepted=base['accepted'],
                    displacement_km=r['projected_arms'].get(arm, {}).get('displacement_from_RF_candidate_km')))
            for kind in values:
                results[cohort][arm][kind] = stats(values[kind])
            for kind in ('unprojected', 'projected'):
                results[cohort][arm][kind]['mean_and_median_improve'] = bool(
                    np.mean(values[kind]) < np.mean(values['incumbent']) and
                    np.median(values[kind]) < np.median(values['incumbent']))
            ax = axes[row, col]
            for kind, color, label in (('incumbent', 'black', 'Published signed prior'),
                    ('unprojected', '#367da4', 'Subset proposals'), ('projected', '#a363a8', 'With gate projection')):
                a = np.sort(values[kind])
                ax.step(np.r_[0, a], np.r_[0, np.arange(1, len(a)+1)/len(a)], where='post', color=color, label=label)
            ax.axvline(.5, color='gray', ls=':')
            ax.set(title=cohort + ' · ' + arm, xlabel='Position error (km)', ylabel='Fraction of complete cohort', ylim=(0, 1.02))
            ax.grid(alpha=.2)
            ax.legend(fontsize=8)
    figure.suptitle('DS23 · multiple-family proposals, with and without original-gate projection\n'
        'All observations and physical priors retained · entire-pair fallback on rejection')
    figure.tight_layout(rect=(0, 0, 1, .93))
    figure.savefig(OUT / 'position_error_distribution.png', dpi=175)
    plt.close(figure)
    confirmed = {kind: all(results[c]['fitted_c'][kind]['mean_and_median_improve'] for c in results)
        for kind in ('unprojected', 'projected')}
    write(OUT / 'evaluation.json', dict(results=results, primary_confirmed=confirmed,
        count=40, goal_population=413, goal_achieved=False, GPS_used_only_here=True,
        verification_sha256=sha(OUT / 'verification.json')))
    with (OUT / 'position_comparison.csv').open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    print(results, flush=True)
    print('Primary confirmed', confirmed, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('verify', 'evaluate'), required=True)
    args = parser.parse_args()
    verify() if args.stage == 'verify' else evaluate()
