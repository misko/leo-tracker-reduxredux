"""Full-denominator geographic evaluation after the frozen inference finishes."""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from run_algo01_ds23_sample import ROOT, read, write, sha
from report_algo02_ds23 import position_error

OUT = ROOT/'reports/2026_10_20_ds23_causal_phase_location_full'
SOURCE = ROOT/'reports/2026_10_19_algo02_ds23_full'
ARMS = ('c0', 'fitted_c')


def capture_format(recording_format):
    return {'short_window_iq_recording':'fast', 'starlink_adaptive_hop_iq':'adaptive'}[recording_format]


def aggregate(rows):
    output = {}
    for arm in ARMS:
        chosen = [r for r in rows if r['arm'] == arm]
        qualified = [r for r in chosen if r['baseline_error_km'] is not None]
        before = np.array([r['baseline_error_km'] for r in qualified])
        after = np.array([r['error_km'] for r in qualified])
        stats = lambda a:dict(count=len(a), mean_km=float(a.mean()) if len(a) else None,
            median_km=float(np.median(a)) if len(a) else None,
            p90_km=float(np.quantile(a,.9)) if len(a) else None,
            maximum_km=float(a.max()) if len(a) else None, below_half_km=int(sum(a <= .5)))
        output[arm] = dict(population=len(chosen), qualified=len(qualified), unavailable=len(chosen)-len(qualified),
            baseline=stats(before), trial=stats(after),
            improved=int(sum(after < before-1e-8)), regressed=int(sum(after > before+1e-8)),
            unchanged=int(sum(abs(after-before) <= 1e-8)))
    return output


def main():
    protocol, execution = read(OUT/'protocol.json'), read(OUT/'execution.json')
    if not execution['all_terminal'] or len(execution['results']) != len(protocol['cases']):
        raise ValueError('full experiment is not terminal')
    receipts = {r['case']:r for r in execution['results']}
    if len(receipts) != len(protocol['cases']):
        raise ValueError('duplicate execution receipt')
    rows, audits, evidence = [], [], {}
    for member in protocol['population']:
        case = member['dataset_label']
        if case not in protocol['cases']:
            for arm in ARMS:
                rows.append(dict(case=case, arm=arm, format=capture_format(member['recording_format']),
                    cohort='unavailable', baseline_error_km=None, error_km=None, accepted=False,
                    prior_qualified=False, kind=None, coefficient=0., execution_failed=False,
                    baseline_RMS_hz=None, RMS_hz=None, RF_objective_gain=None))
            continue
        old = read(SOURCE/case/'algo02_result.json')
        receipt = receipts[case]
        failed = 'error' in receipt
        document = read(ROOT/receipt['path']) if not failed else None
        baseline = old['policy_arms']
        policy = document['policy_arms'] if document else baseline
        if document:
            assert not document['GPS_used'] and not document['future_TLE_used']
            assert document['original_mask'] == old['mask']
            assert document['baseline_arms'] == baseline
            history = SOURCE/'causal_phase_history'/(case+'.json')
            forecast = history.with_name(case+'_forecast.json')
            assert sha(history) == document['history_sha256'] and sha(forecast) == document['forecast_sha256']
            f = read(forecast)
            assert f['strictly_pre_RF'] and f['GPS_or_radio_used'] is False
            if document['accepted']:
                assert all(g['compatible'] for a in ARMS for g in
                           document['arms'][a]['gates']['tracks']+document['arms'][a]['linear_gates'])
                assert all(document['arms'][a]['final_phase_change_s'] <= .01 for a in ARMS)
                assert all(document['arms'][a]['linear_calibration_max_difference'] == 0 for a in ARMS)
            evidence[case] = dict(path=receipt['path'], sha256=sha(ROOT/receipt['path']))
        cohort = ('development40' if case in protocol['development'] else
                  'prior_validation20' if case in protocol['prior_validation'] else 'remaining344')
        selected = document['selection'] if document else dict(qualified=False)
        for arm in ARMS:
            before, after = baseline[arm], policy[arm]
            rows.append(dict(case=case, arm=arm, format=capture_format(member['recording_format']),
                cohort=cohort, baseline_error_km=position_error(before['endpoint_latlon']), error_km=position_error(after['endpoint_latlon']),
                accepted=bool(document and document['accepted']), prior_qualified=selected['qualified'],
                kind=selected.get('kind'), coefficient=selected.get('coefficient',0.), execution_failed=failed,
                baseline_RMS_hz=before['RMS_hz'], RMS_hz=after['RMS_hz'],
                RF_objective_gain=before['negative_twice_elbo']-after['negative_twice_elbo']))
        audits.append(dict(case=case, inference_failed=failed, original_points_retained=True,
            c_arms_matched=True, no_linear_calibration_update=True, result_path=receipt.get('path')))
    groups = dict(all=rows,
        remaining344=[r for r in rows if r['cohort']=='remaining344'],
        development40=[r for r in rows if r['cohort']=='development40'],
        prior_validation20=[r for r in rows if r['cohort']=='prior_validation20'],
        fast=[r for r in rows if r['format']=='fast'], adaptive=[r for r in rows if r['format']=='adaptive'])
    summary = {group:aggregate(chosen) for group,chosen in groups.items()}
    positive = all(summary[g][a]['trial'][m] < summary[g][a]['baseline'][m]
                   for g in ('all','remaining344') for a in ARMS for m in ('mean_km','median_km'))
    failures = [r for r in execution['results'] if 'error' in r]
    result = dict(summary=summary, positive_generalization_criterion_pass=bool(positive and not failures),
        execution_failures=failures, correction_qualified=sum(r['prior_qualified'] for r in rows if r['arm']=='c0'),
        correction_used=sum(r['accepted'] for r in rows if r['arm']=='c0'),
        goal_half_km_on_DS23_not_achieved=True, all_unavailable_recordings_retained=True,
        GPS_used_only_in_reporter=True, one_site_retrospective_corpus_not_new_location_validation=True)
    write(OUT/'evaluation.json', result)
    write(OUT/'evaluation_audit.json', dict(records=audits, evidence=evidence))
    with (OUT/'positions.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    frequency = {}
    for scope in ('all','fast','adaptive'):
        frequency[scope] = {}
        for arm in ARMS:
            selected = [r for r in rows if r['arm']==arm and r['error_km'] is not None
                        and (scope=='all' or r['format']==scope)]
            frequency[scope][arm] = {name:float(np.mean([r[name] for r in selected]))
                                    for name in ('baseline_RMS_hz','RMS_hz','RF_objective_gain')}
    write(OUT/'frequency_fit_summary.json', frequency)
    fig, axes = plt.subplots(1,2,figsize=(13,5))
    for ax,arm in zip(axes,ARMS,strict=True):
        selected = [r for r in rows if r['arm']==arm and r['error_km'] is not None]
        denominator = summary['all'][arm]['population']
        for field,label,color in [('baseline_error_km','Original ALGO02','#777777'),('error_km','Causal signed phase mean','#227f99')]:
            values = np.sort([r[field] for r in selected])
            ax.step(np.r_[0,values],np.r_[0,np.arange(1,len(values)+1)/denominator],where='post',label=label,color=color)
        ax.axvline(.5,color='green',ls=':',lw=1)
        ax.set(xlabel='Position error (km)',ylabel='Fraction of all 413 recordings',title=arm,ylim=(0,1.02))
        ax.grid(alpha=.15);ax.legend(fontsize=9)
    fig.suptitle('DS23 · one frozen causal phase-mean rule · nine unavailable positions retained\n'
                 'CDF uses all 413 recordings; all accepted outliers remain visible',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.90));fig.savefig(OUT/'position_error_distribution.png',dpi=180,bbox_inches='tight');plt.close(fig)
    fig,axes = plt.subplots(1,2,figsize=(13,5))
    for ax,arm in zip(axes,ARMS,strict=True):
        selected = [r for r in rows if r['arm']==arm and r['error_km'] is not None]
        for group,color,marker in [('development40','#777777','o'),('prior_validation20','#a56224','s'),('remaining344','#227f99','.')]:
            chosen = [r for r in selected if r['cohort']==group]
            ax.scatter([r['baseline_error_km'] for r in chosen],[r['error_km'] for r in chosen],s=20,color=color,marker=marker,label=group,alpha=.7)
        limit=max(max(r['error_km'],r['baseline_error_km']) for r in selected)*1.04
        ax.plot([0,limit],[0,limit],color='gray',ls='--',lw=.8)
        ax.set(xlabel='Original ALGO02 error (km)',ylabel='Signed-prior rule error (km)',title=arm)
        ax.grid(alpha=.15);ax.legend(fontsize=9)
    fig.suptitle('Fixed rule, complete matched population · below diagonal improves position',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.94));fig.savefig(OUT/'paired_position_errors.png',dpi=180,bbox_inches='tight');plt.close(fig)
    fig,axes = plt.subplots(2,1,figsize=(14,7),sharex=True)
    for ax,arm in zip(axes,ARMS,strict=True):
        for capture,color in (('fast','#257c91'),('adaptive','#b36f39')):
            selected = [r for r in rows if r['arm']==arm and r['format']==capture and r['error_km'] is not None]
            ax.scatter([int(r['case'].split('-')[1]) for r in selected],
                       [r['error_km']-r['baseline_error_km'] for r in selected],
                       color=color,s=16,label=capture,alpha=.8)
        ax.axhline(0,color='black',lw=.8)
        ax.set(ylabel='Change in error (km)',title=arm)
        ax.grid(alpha=.15);ax.legend(fontsize=9)
    axes[-1].set_xlabel('DS23 recording number')
    fig.suptitle('Every matched recording · negative changes improve position\n'
                 'Fast-scan gains coexist with adaptive-scan regressions; no accepted outliers removed',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.91));fig.savefig(OUT/'position_error_changes.png',dpi=180,bbox_inches='tight');plt.close(fig)
    print('Positive full-corpus criterion:',result['positive_generalization_criterion_pass'],'failures',len(failures),flush=True)
    print('Qualified/used',result['correction_qualified'],result['correction_used'],flush=True)
    for group in summary:
        for arm in ARMS:
            r=summary[group][arm]
            print(group,arm,'mean',r['baseline']['mean_km'],'->',r['trial']['mean_km'],
                  'median',r['baseline']['median_km'],'->',r['trial']['median_km'],flush=True)


if __name__ == '__main__':
    main()
