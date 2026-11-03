"""RF replay before geographic evaluation of multiple-family proposals."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from algo02_scan import pair_passes
from ds23_multifamily_proposals import family_masks, score_position
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_fft_grid_position import setup
from probe_ds23_multifamily_proposals import OUT, ARMS, prepare
from probe_ds23_frequency_events import summary
from run_algo01_ds23_sample import read, write, sha


def verify_case(case):
    path = OUT / (case + '.json')
    record = read(path)
    scan, node, keep, base, old, signed, binding, model, powers, means, entries = setup(case)
    if binding != record['incumbent_binding'] or record['incumbent_arms'] != signed['policy_arms']:
        raise ValueError('incumbent receipt changed')
    np.testing.assert_array_equal(keep, record['original_mask'])
    labels = np.asarray(base.labels)[base.flat_labels]
    checks = []
    for trial in record['trials']:
        train = family_masks(labels, keep, trial['families'])
        if int(train.sum()) != trial['train_points']:
            raise ValueError('subset training mask changed')
        predictive = [e for e in entries if e['candidate_index'] in trial['families']]
        if sum(e['points'] for e in predictive) != trial['train_predictive_points']:
            raise ValueError('omitted family appeared in predictive training')
        for s in trial['scores'].values():
            if s['scored_original_curved_points'] != int(keep.sum()) or sum(f['points'] for f in s['folds']) != int(keep.sum()):
                raise ValueError('predictive score changes observation population')
    selected = next((t for t in record['trials'] if t['index'] == record['selected_index']), None)
    eligible = [t for t in record['trials'] if t['qualified']]
    if eligible and selected['index'] != min(eligible, key=lambda t: t['scores']['c0']['score'])['index']:
        raise ValueError('proposal selected by a different criterion')
    for arm in ARMS:
        for name, position, saved in ([('null', record['incumbent_arms'][arm]['endpoint_east_north_km'], record['null_scores'][arm])]
                if record['null_scores'] else []):
            fresh = score_position(scan, node, keep, arm, powers, means, model, np.asarray(position))
            if abs(fresh['score'] - saved['score']) > 1e-6:
                raise ValueError('null full-family score changed')
            checks.append(dict(arm=arm, mode=name, score_difference=fresh['score']-saved['score']))
        if selected:
            fresh = score_position(scan, node, keep, arm, powers, means, model,
                np.asarray(selected['arms'][arm]['endpoint_east_north_km']))
            saved = selected['scores'][arm]
            if abs(fresh['score'] - saved['score']) > 1e-6:
                raise ValueError('selected full-family score changed')
            checks.append(dict(arm=arm, mode='selected', score_difference=fresh['score']-saved['score']))
        if record['selected_full_arms']:
            saved = record['selected_full_arms'][arm]
            p = make_event_problem(scan, node, keep, arm, np.asarray(saved['phase_reference']), powers, means, model, [])
            attach_event_predictive(p, entries, powers)
            fresh = summary(p, np.asarray(saved['endpoint_east_north_km']), entries)
            if abs(fresh['negative_twice_elbo'] - saved['negative_twice_elbo']) > 1e-3:
                raise ValueError('full original-data candidate changed')
            if [r['compatible'] for r in fresh['gates']['tracks'] + fresh['linear_gates']] != [r['compatible'] for r in saved['gates']['tracks'] + saved['linear_gates']]:
                raise ValueError('full original-data gates changed')
    positive = bool(selected and all(s['qualified'] for s in record['null_scores'].values()) and
                    all(g > 2*np.log(7) for g in record['score_gains'].values()))
    accepted = bool(positive and pair_passes(record['selected_full_arms'], include_linear=True))
    if accepted != record['accepted']:
        raise ValueError('saved policy differs from declared RF/gate acceptance')
    if record['policy_arms'] != (record['selected_full_arms'] if accepted else record['incumbent_arms']):
        raise ValueError('policy or exact incumbent fallback changed')
    return dict(case=case, fit_sha256=sha(path), accepted=accepted, checks=checks,
        no_GPS_read=True, all_original_data_restored_in_gate_replay=True)


def verify(part):
    protocol = prepare()
    cases = protocol[part + '_cases'] if part == 'pilot' else protocol['development_cases'] + protocol['confirmation_cases']
    receipts, errors = [], []
    with ProcessPoolExecutor(max_workers=min(16, len(cases))) as pool:
        futures = {pool.submit(verify_case, c): c for c in cases}
        for future in as_completed(futures):
            try:
                receipts.append(future.result())
            except Exception as exc:
                errors.append(dict(case=futures[future], error=repr(exc)))
            write(OUT / ('verification_' + part + '_progress.json'), dict(completed=len(receipts)+len(errors), total=len(cases)))
    write(OUT / ('verification_' + part + '.json'), dict(receipts=receipts, errors=errors,
        all_terminal=True, qualified=not errors and len(receipts)==len(cases), no_GPS_read=True))
    print('Verified', len(receipts), 'errors', errors, flush=True)


def stats(values):
    a = np.asarray(values)
    return dict(count=len(a), mean_km=float(a.mean()), median_km=float(np.median(a)),
        p90_km=float(np.quantile(a, .9)), below_half_km=int(np.sum(a <= .5)))


def evaluate():
    protocol = prepare()
    validation = read(OUT / 'verification_all.json')
    if not validation['qualified'] or len(validation['receipts']) != 40:
        raise ValueError('complete RF verification required before GPS evaluation')
    bindings = {r['case']: r['fit_sha256'] for r in validation['receipts']}
    from report_algo02_ds23 import position_error
    rows, results = [], {}
    figure, axes = plt.subplots(2, 2, figsize=(13, 9))
    for row, cohort in enumerate(('development', 'confirmation')):
        results[cohort] = {}
        for col, arm in enumerate(ARMS):
            before, after = [], []
            ax = axes[row, col]
            for case in protocol[cohort + '_cases']:
                path = OUT / (case + '.json')
                if sha(path) != bindings[case]:
                    raise ValueError('fit changed after verification')
                r = read(path)
                before.append(position_error(r['incumbent_arms'][arm]['endpoint_latlon']))
                after.append(position_error(r['policy_arms'][arm]['endpoint_latlon']))
                rows.append(dict(case=case, cohort=cohort, arm=arm, accepted=r['accepted'],
                    incumbent_error_km=before[-1], policy_error_km=after[-1],
                    score_gain=r['score_gains'].get(arm),
                    selected_index=r['selected_index'],
                    full_candidate_gates_pass=pair_passes(r['selected_full_arms'], include_linear=True) if r['selected_full_arms'] else False))
            results[cohort][arm] = dict(incumbent=stats(before), policy=stats(after),
                mean_and_median_improve=bool(np.mean(after) < np.mean(before) and np.median(after) < np.median(before)),
                accepted=sum(r['accepted'] for r in rows if r['cohort']==cohort and r['arm']==arm))
            for values, color, label in ((before, 'black', 'Published signed prior'), (after, '#367da4', 'Multiple-family proposals')):
                a = np.sort(values)
                ax.step(np.r_[0, a], np.r_[0, np.arange(1, len(a)+1)/len(a)], where='post', color=color, label=label)
            ax.axvline(.5, color='gray', ls=':')
            ax.set(title=cohort + ' · ' + arm, xlabel='Position error (km)', ylabel='Fraction of complete cohort', ylim=(0, 1.02))
            ax.grid(alpha=.2)
            ax.legend(fontsize=8)
    figure.suptitle('DS23 · cold multiple-family proposals; full cross-family RF scoring\n'
        'Every original observation restored for final gates; exact incumbent fallback on rejection')
    figure.tight_layout(rect=(0, 0, 1, .93))
    figure.savefig(OUT / 'position_error_distribution.png', dpi=175)
    plt.close(figure)
    primary = all(results[p]['fitted_c']['mean_and_median_improve'] for p in results)
    write(OUT / 'evaluation.json', dict(results=results, primary_confirmed=primary,
        goal_achieved=False, count=40, goal_population=413, GPS_used_only_here=True,
        verification_sha256=sha(OUT / 'verification_all.json')))
    with (OUT / 'position_comparison.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    print(results, flush=True)
    print('Primary confirmed', primary, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('verify-pilot', 'verify-all', 'evaluate'), required=True)
    args = parser.parse_args()
    evaluate() if args.stage == 'evaluate' else verify('pilot' if args.stage=='verify-pilot' else 'all')
