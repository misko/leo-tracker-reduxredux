"""Report-side position evaluation of the completed predictive descent pilots."""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_predictive_position_descent import OUT,full_at,COHORT
from resume_ds23_predictive_position_descent import OUT as RECOVERY
from probe_ds23_sign_carrier_position import context_signed
from ds23_multifamily_proposals import score_position
from report_algo02_ds23 import position_error
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha


def main():
    original=read(OUT/'evaluation.json');recovered=read(RECOVERY/'evaluation.json')
    if not original['all_terminal'] or not recovered['all_terminal']:raise ValueError('pilot still live')
    replacements={r['case']:r for r in recovered['rows']};rows=[];checks=[];paths=[]
    random=set(read(COHORT)['pilot_cases'])
    for previous in original['rows']:
        record=replacements.get(previous['case'],previous);case=record['case'];context=context_signed(case)
        if record['status']!='complete':raise ValueError('pilot remains failed after bounded recovery')
        scan,node,mask,powers,means,model,entries,signed,_=context
        acceptance=bool(all(r['converged'] for r in record['searches'].values())
            and all(g>2*np.log(2) for g in record['score_gains'].values())
            and all(record['null_scores'][a]['cross_family']['qualified'] and record['candidate_scores'][a]['cross_family']['qualified'] for a in ['c0','fitted_c'])
            and valid(record['arms']))
        if acceptance!=record['accepted']:raise ValueError('fixed RF selection rule failed replay')
        for arm in ['c0','fitted_c']:
            candidate=record['arms'][arm];xy=np.asarray(candidate['endpoint_east_north_km'])
            full=full_at(context,arm,xy);delta=full['negative_twice_elbo']-candidate['negative_twice_elbo']
            if abs(delta)>1e-6:raise ValueError('original full-data endpoint failed replay')
            cross=score_position(scan,node,mask,arm,powers,means,model,xy)
            expected=record['candidate_scores'][arm]['cross_family'];score_delta=cross['score']-expected['score']
            if abs(score_delta)>1e-5:raise ValueError('serial predictive candidate score failed replay')
            checks.append(dict(case=case,arm=arm,original_full_ELBO_difference=delta,predictive_score_difference=score_delta,
                every_curved_observation_scored_once=cross['scored_original_curved_points']==int(mask.sum())))
            rows.append(dict(case=case,arm=arm,cohort='preexisting_random_pilot' if case in random else 'engineering',
                accepted=acceptance,original_error_km=position_error(record['incumbent_arms'][arm]['endpoint_latlon']),
                candidate_error_km=position_error(candidate['endpoint_latlon']),
                policy_error_km=position_error(record['policy_arms'][arm]['endpoint_latlon']),
                candidate_frequency_RMS_hz=candidate['RMS_hz'],original_frequency_RMS_hz=record['incumbent_arms'][arm]['RMS_hz'],
                candidate_curved_gate_failures=sum(not r['compatible'] for r in candidate['gates']['tracks']),
                candidate_linear_gate_failures=sum(not r['compatible'] for r in candidate['linear_gates']),
                cross_family_score_gain=record['score_gains'][arm],optimizer_converged=record['searches'][arm]['converged']))
            history=record['searches'][arm]['history']
            paths.append(dict(case=case,arm=arm,accepted=acceptance,path=np.vstack((np.zeros(2),
                [r['position'] for r in history],record['searches'][arm]['position'])),
                original=record['incumbent_arms'][arm]['endpoint_east_north_km']))
    aggregate=[]
    for cohort in ['engineering','preexisting_random_pilot']:
        for arm in ['c0','fitted_c']:
            selected=[r for r in rows if r['cohort']==cohort and r['arm']==arm]
            aggregate.append(dict(cohort=cohort,arm=arm,cases=len(selected),accepted=sum(r['accepted'] for r in selected),
                original_mean_km=float(np.mean([r['original_error_km'] for r in selected])),
                original_median_km=float(np.median([r['original_error_km'] for r in selected])),
                policy_mean_km=float(np.mean([r['policy_error_km'] for r in selected])),
                policy_median_km=float(np.median([r['policy_error_km'] for r in selected]))))
    cases=[r['case'] for r in original['rows']];fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    x=np.arange(len(cases))
    for ax,arm in zip(axes,['c0','fitted_c'],strict=True):
        selected=[next(r for r in rows if r['case']==case and r['arm']==arm) for case in cases]
        ax.scatter(x-.12,[r['original_error_km'] for r in selected],color='black',label='Original signed incumbent')
        ax.scatter(x+.12,[r['policy_error_km'] for r in selected],color='seagreen',label='Gate-qualified policy')
        ax.scatter(x,[r['candidate_error_km'] for r in selected],facecolors='none',edgecolors='purple',label='Raw predictive minimum')
        for k,r in enumerate(selected):
            if not r['accepted']:ax.scatter(k,r['candidate_error_km'],color='crimson',marker='x',s=50)
        ax.axhline(.5,color='gray',ls='--',lw=1);ax.set_xticks(x,[c.split('-')[1] for c in cases]);ax.grid(alpha=.2)
        ax.set(title=arm,ylabel='Position error (km)',xlabel='Pilot scan');ax.legend(fontsize=8)
    fig.suptitle('Direct cross-family predictive descent · original labels and residual gates\n'
        'Red crosses rejected; all pilots retained; accuracy evaluated only after RF selection',fontsize=11)
    fig.savefig(OUT/'position_comparison.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,6),layout='constrained')
    for ax,arm in zip(axes,['c0','fitted_c'],strict=True):
        for k,case in enumerate(cases):
            r=next(v for v in paths if v['case']==case and v['arm']==arm);path=np.asarray(r['path']);color=plt.get_cmap('tab10')(k)
            ax.plot(path[:,0],path[:,1],'.-',color=color,lw=1,label=case.split('-')[1])
            ax.scatter(*path[-1],marker='o' if r['accepted'] else 'x',color=color,s=65)
            ax.scatter(*r['original'],marker='s',facecolors='none',edgecolors=color,s=55)
        ax.scatter(0,0,color='black',marker='*',s=90,label='Regional cold start')
        ax.set(xlim=(-12.5,12.5),ylim=(-12.5,12.5),aspect='equal',title=arm,
            xlabel='East from regional centre (km)',ylabel='North from regional centre (km)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Accepted optimizer steps · circles pass policy, crosses reject, squares original endpoints\n'
        'These prototype paths are not a replacement for complete DBG01 regional restart maps',fontsize=11)
    fig.savefig(OUT/'cold_descent_paths.png',dpi=160);plt.close(fig)
    write(OUT/'independent_replay_evaluation.json',dict(rows=rows,aggregate=aggregate,checks=checks,
        original_evaluation_sha256=sha(OUT/'evaluation.json'),recovery_evaluation_sha256=sha(RECOVERY/'evaluation.json'),
        all_original_full_endpoints_and_predictive_scores_replayed=True,
        no_GT_used_in_optimization_or_policy=True,no_full_DS23_or_new_location_generalization_claim=True))
    print(rows,flush=True);print('aggregate',aggregate,flush=True)


if __name__=='__main__':main()
