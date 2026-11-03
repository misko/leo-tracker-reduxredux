"""Independent all-factor RF replay before reporting any geographic errors."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_unknown_polynomial import unknown_ledger, make_unknown_problem
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import summary
from probe_ds23_unknown_polynomial import OUT, ARMS, prepare, active_change, pair_valid
from run_algo01_ds23_sample import ROOT, read, write, sha


def verify_case(case):
    directory=OUT/case;record=read(directory/'result.json');screen=read(directory/'screen.json')
    scan,node,keep,base,old,signed,binding,model,powers,means,entries=setup(case)
    if binding!=record['incumbent_binding'] or signed['policy_arms']!=record['incumbent_arms']:
        raise ValueError('incumbent evidence changed')
    if sha(directory/'screen.json')!=record['screen_sha256']:
        raise ValueError('screen changed')
    np.testing.assert_array_equal(keep,record['original_mask'])
    ledger=unknown_ledger(base,keep,entries,powers)
    if {str(k):v for k,v in ledger.items()}!=screen['ledger']:
        raise ValueError('unknown density normalization or ownership does not replay')
    original_ids=sorted(oid for rows in ledger.values() for r in rows for oid in r['observation_ids'])
    if original_ids!=record['original_position_observation_ids']:
        raise ValueError('full original evidence measure changed')
    checked=[];fresh_valid=[]
    for trial in record['trials']:
        unknown=trial['unknown_families'];pair={}
        for arm in ARMS:
            r=trial['arms'][arm];x=np.asarray(r['endpoint_east_north_km'])
            p=make_unknown_problem(scan,node,keep,arm,np.asarray(r['phase_reference']),powers,means,model,entries,unknown,ledger)
            fresh=summary(p,x,p.known_entries)
            phase,change,bounded=active_change(p,x)
            fresh.update(final_phase_change_s=change,active_phases_bounded=bounded)
            if abs(fresh['negative_twice_elbo']-r['negative_twice_elbo'])>1e-3:
                raise ValueError('full known-plus-unknown objective does not replay')
            old_gates=[g['compatible'] for g in r['gates']['tracks']+r['linear_gates']]
            new_gates=[g['compatible'] for g in fresh['gates']['tracks']+fresh['linear_gates']]
            if old_gates!=new_gates or abs(change-r['final_phase_change_s'])>1e-8:
                raise ValueError('known gates or phase convergence changed')
            known_ids=[oid for row,i,sl in zip(p.rows,p.members,p.slices,strict=True)
                for oid in np.asarray(scan.tracks[i]['observation_ids'])[p.keep[sl]]]
            known_ids += [oid for e in p.known_entries for oid in e['observation_ids']]
            unknown_ids=[oid for row in p.unknown_rows for oid in row['observation_ids']]
            if set(known_ids)&set(unknown_ids) or sorted(known_ids+unknown_ids)!=original_ids:
                raise ValueError('measurement omitted, duplicated or scored in both components')
            if fresh['linear_calibration_max_difference']>1e-10:
                raise ValueError('predictive points changed calibration')
            if r['all_original_scored_points']!=len(original_ids) or r['unknown_points']!=len(unknown_ids):
                raise ValueError('point accounting changed')
            checked.append(dict(unknown=unknown,arm=arm,known_points=len(known_ids),unknown_points=len(unknown_ids),
                RF_difference=fresh['negative_twice_elbo']-r['negative_twice_elbo']))
            pair[arm]=fresh
        valid=pair_valid(pair)
        if trial['paired_valid']!=valid:
            raise ValueError('trial validity changed')
        fresh_valid.append(valid)
    null=record['trials'][0]
    reference={arm:min(record['normalized_incumbent_costs'][arm],null['arms'][arm]['negative_twice_elbo'])
        if null['paired_valid'] else record['normalized_incumbent_costs'][arm] for arm in ARMS}
    if reference!=record['reference_costs']:
        raise ValueError('matched null reference changed')
    candidates=[t for t in record['trials'][1:] if t['paired_valid'] and all(
        reference[a]-t['arms'][a]['negative_twice_elbo']>2*np.log(2) for a in ARMS)]
    winner=min(candidates,key=lambda t:t['arms']['c0']['negative_twice_elbo']) if candidates else None
    if record['accepted']!=(winner is not None) or record['policy_arms']!=(winner['arms'] if winner else record['incumbent_arms']):
        raise ValueError('selection or exact fallback changed')
    if record['selected_unknown_families']!=(winner['unknown_families'] if winner else []):
        raise ValueError('selected family set changed')
    return dict(case=case,checks=checked,result_sha256=sha(directory/'result.json'),no_GPS_used=True)


def verify(part):
    protocol=prepare();cases=protocol['pilot_cases'] if part=='pilot' else protocol['development_cases']+protocol['confirmation_cases']
    receipts=[];errors=[]
    with ProcessPoolExecutor(max_workers=min(16,len(cases))) as pool:
        jobs={pool.submit(verify_case,c):c for c in cases}
        for f in as_completed(jobs):
            try:receipts.append(f.result())
            except Exception as exc:errors.append(dict(case=jobs[f],error=repr(exc)))
    write(OUT/(part+'_verification.json'),dict(all_terminal=True,qualified=not errors and len(receipts)==len(cases),
        receipts=receipts,errors=errors,no_GPS_used=True))
    print('Verified',len(receipts),'errors',errors,flush=True)


def stats(values):
    a=np.asarray(values)
    return dict(count=len(a),mean_km=float(np.mean(a)),median_km=float(np.median(a)),
        p90_km=float(np.quantile(a,.9)),below_half_km=int(np.sum(a<=.5)))


def evaluate():
    protocol=prepare();audit=read(OUT/'cohort_verification.json')
    if not audit['qualified'] or len(audit['receipts'])!=40:
        raise ValueError('all 40 RF and ownership replays required before GPS evaluation')
    from report_algo02_ds23 import position_error
    bindings={r['case']:r for r in audit['receipts']};results={};rows=[];accepted=[]
    figure,axes=plt.subplots(2,2,figsize=(13,9))
    for row,cohort in enumerate(('development','confirmation')):
        results[cohort]={}
        for col,arm in enumerate(ARMS):
            values={k:[] for k in ('incumbent','cold_null','unknown_policy')}
            for case in protocol[cohort+'_cases']:
                path=OUT/case/'result.json'
                if sha(path)!=bindings[case]['result_sha256']:
                    raise ValueError('verified result bytes changed')
                r=read(path);before=position_error(r['incumbent_arms'][arm]['endpoint_latlon'])
                after=position_error(r['policy_arms'][arm]['endpoint_latlon'])
                cold=r['cold_null'];cold_arm=cold['arms'][arm] if cold['paired_valid'] else r['incumbent_arms'][arm]
                values['incumbent'].append(before);values['unknown_policy'].append(after)
                values['cold_null'].append(position_error(cold_arm['endpoint_latlon']))
                labels=r['selected_unknown_families'];unknown_ids=[]
                if r['accepted']:
                    ledger=read(OUT/case/'screen.json')['ledger']
                    unknown_ids=[oid for j in labels for entry in ledger[str(j)] for oid in entry['observation_ids']]
                rows.append(dict(case=case,cohort=cohort,arm=arm,accepted=r['accepted'],
                    unknown_norads=','.join(str(r['norad_by_label'][str(j)]) for j in labels),
                    unknown_original_position_points=len(unknown_ids),
                    original_position_points=len(r['original_position_observation_ids']),
                    incumbent_error_km=before,policy_error_km=after,cold_null_error_km=values['cold_null'][-1],
                    known_RF_RMS_before_hz=r['incumbent_arms'][arm]['RMS_hz'],known_RF_RMS_after_hz=r['policy_arms'][arm]['RMS_hz'],
                    RF_RMS_masks_differ_if_unknown=r['accepted']))
                if arm=='fitted_c' and r['accepted']:
                    accepted.append(rows[-1])
            results[cohort][arm]={name:stats(v) for name,v in values.items()}
            results[cohort][arm]['mean_and_median_improve']=bool(
                np.mean(values['unknown_policy'])<np.mean(values['incumbent']) and
                np.median(values['unknown_policy'])<np.median(values['incumbent']))
            ax=axes[row,col]
            for key,color,label in (('incumbent','black','Published signed prior'),('cold_null','#718c9d','Matched cold all-known control'),('unknown_policy','#bb6b36','Satellite/unknown MAP policy')):
                a=np.sort(values[key]);ax.step(np.r_[0,a],np.r_[0,np.arange(1,len(a)+1)/len(a)],where='post',color=color,label=label)
            ax.axvline(.5,color='gray',ls=':');ax.grid(alpha=.15)
            ax.set(title=cohort+' · '+arm,xlabel='Position error (km)',ylabel='Fraction of complete cohort',ylim=(0,1.02));ax.legend(fontsize=8)
    figure.suptitle('DS23 · satellite versus unknown-polynomial model\nEvery original position observation scored; unchanged known residual gates and paired-c fallback')
    figure.tight_layout(rect=(0,0,1,.92));figure.savefig(OUT/'position_error_distribution.png',dpi=175);plt.close(figure)
    margins=[]
    for case in protocol['development_cases']+protocol['confirmation_cases']:
        r=read(OUT/case/'result.json');trials=r['trials'][1:]
        all_best=max(min(t['coded_gains'].values()) for t in trials)
        valid=[min(t['coded_gains'].values()) for t in trials if t['paired_valid']]
        margins.append(dict(case=case,best_both_arm_gain=all_best,
            best_gate_passing_both_arm_gain=max(valid) if valid else None,
            unknown_trials=len(trials),gate_passing_unknown_trials=len(valid)))
    ordered=sorted(margins,key=lambda r:r['best_both_arm_gain'],reverse=True)
    fig,ax=plt.subplots(figsize=(14,5))
    xs=np.arange(len(ordered))
    ax.bar(xs,[r['best_both_arm_gain'] for r in ordered],color='#6686aa',label='Best unknown alternative, before gates')
    ax.scatter(xs,[r['best_gate_passing_both_arm_gain'] if r['best_gate_passing_both_arm_gain'] is not None else np.nan for r in ordered],
        color='#ba6943',s=18,label='Best alternative passing original gates',zorder=3)
    ax.axhline(0,color='black',lw=.8);ax.axhline(2*np.log(2),color='gray',ls=':',label='Required adoption gain')
    ax.set_xticks(xs,[r['case'].replace('DS23-','') for r in ordered],rotation=90,fontsize=7)
    ax.set(xlabel='DS23 scan',ylabel='Penalized full-observation RF gain\nMinimum of the matched c0 and fitted-c gains',
        title='Unknown-family alternatives lose on score in all 40 scans\n240 single/pair alternatives; positive values favor unknown; every original factor scored')
    ax.grid(axis='y',alpha=.15);ax.legend(fontsize=8);fig.tight_layout()
    fig.savefig(OUT/'unknown_score_margins.png',dpi=175);plt.close(fig)
    write(OUT/'score_margin_audit.json',dict(rows=margins,
        total_unknown_trials=sum(r['unknown_trials'] for r in margins),
        gate_passing_unknown_trials=sum(r['gate_passing_unknown_trials'] for r in margins),
        trials_positive_in_both_arms=sum(min(t['coded_gains'].values())>0
            for case in protocol['development_cases']+protocol['confirmation_cases']
            for t in read(OUT/case/'result.json')['trials'][1:]),
        cannot_certify_original_satellite_identities=True,
        conditional_on_fixed_polynomial_prior_and_finite_hypothesis_budget=True))
    primary=all(results[c]['fitted_c']['mean_and_median_improve'] for c in results)
    write(OUT/'evaluation.json',dict(results=results,accepted_scans=accepted,primary_confirmed=primary,
        count=40,goal_population=413,goal_achieved=False,GPS_used_only_here=True,
        verification_sha256=sha(OUT/'cohort_verification.json'),
        unknown_polynomial_fits_not_satellite_associations=True,RF_RMS_across_changed_masks_not_a_localization_claim=True))
    with (OUT/'position_comparison.csv').open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    print('Primary confirmed',primary,'adopted',len(accepted),'results',results,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('verify-pilot','verify-cohort','evaluate'),required=True)
    stage=parser.parse_args().stage
    evaluate() if stage=='evaluate' else verify('pilot' if stage=='verify-pilot' else 'cohort')
