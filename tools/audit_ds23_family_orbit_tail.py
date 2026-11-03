"""Independent disabled-coupling replay and report-only position evaluation."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import ds23_family_orbit_tail as helper
from ds23_frequency_events import attach_event_predictive
from probe_ds23_fft_grid_position import setup
from run_ds23_family_orbit_tail_v2 import OUT,bind
from run_algo01_ds23_sample import ROOT,read,write,sha


def phase_only_groups(begin,labels,supported,members):
    groups=helper.family_groups_original(begin,labels,supported,members)
    groups[begin+len(labels):begin+len(labels)+3*len(supported)]=-1
    return groups


def replay(case):
    # Preserve the new helper's whole pipeline. Disable just the additional
    # grouping of the three shape coordinates with their own phase coordinate.
    scan,node,keep,base,old,signed,binding,model,powers,means,entries=setup(case)
    helper.family_groups_original=helper.family_groups
    helper.family_groups=phase_only_groups
    nulls=[];influence=[]
    try:
        for arm in ('c0','fitted_c'):
            saved=signed['policy_arms'][arm]
            p=helper.make_joint_tail_problem(scan,node,keep,arm,np.asarray(saved['phase_reference']),powers,means,model)
            attach_event_predictive(p,entries,powers)
            c=p.calculate(np.asarray(saved['endpoint_east_north_km']))
            delta=c['negative_twice_elbo']-saved['negative_twice_elbo']
            if abs(delta)>1e-3:raise ValueError('new factory with coupling disabled does not reproduce baseline')
            nulls.append(dict(arm=arm,RF_difference=delta))
    finally:
        helper.family_groups=helper.family_groups_original
        del helper.family_groups_original
    record=read(OUT/(case+'.json'))
    if record['qualified']:
        for arm in ('c0','fitted_c'):
            saved=record['arms'][arm]
            p=helper.make_joint_tail_problem(scan,node,keep,arm,np.asarray(saved['phase_reference']),powers,means,model)
            attach_event_predictive(p,entries,powers)
            c=p.calculate(np.asarray(saved['endpoint_east_north_km']))
            if abs(c['negative_twice_elbo']-saved['negative_twice_elbo'])>1e-3:
                raise ValueError('joint-tail saved endpoint no longer replays')
            begin=p.hardware.shape[1]+p.smooth.shape[1]
            coefficient=c['latent_coefficient']
            for j in p.supported:
                k=p.supported.index(j);local=p.labels.index(j)
                indices=[begin+local,*range(begin+len(p.labels)+3*k,begin+len(p.labels)+3*k+3)]
                indices=np.array(indices)
                precision=float(c['coefficient_prior_precision'][indices[0]])
                family=dict(case=case,arm=arm,norad=int(scan.norads[j]),
                    phase_prior_standard_deviation_s=float(p.phase_sigma[local]),
                    latent_phase_z=float(coefficient[indices[0]]),
                    shape_standardized_norm=float(np.linalg.norm(coefficient[indices[1:]])),
                    shared_family_precision=precision,
                    added_shape_penalty=float(np.sum(coefficient[indices[1:]]**2)*precision))
                influence.append(family)
    return dict(case=case,nulls=nulls,families=influence)


def stats(x):
    x=np.asarray(x)
    return dict(count=len(x),mean_km=float(x.mean()),median_km=float(np.median(x)),
                maximum_km=float(x.max()),below_half_km=int(np.sum(x<=.5)))


def main():
    protocol=bind();cases=protocol['development_cases']+protocol['confirmation_cases']
    for cohort in ('development','confirmation'):
        e=read(OUT/(cohort+'_execution.json'))
        if not e['all_terminal'] or len(e['receipts'])!=len(protocol[cohort+'_cases']) or any('error' in r for r in e['receipts']):
            raise ValueError('full matched cohorts are not complete')
    replays=[]
    with ProcessPoolExecutor(max_workers=12) as pool:
        futures={pool.submit(replay,c):c for c in cases}
        for f in as_completed(futures):replays.append(f.result())
    # Geographic evaluation is deliberately isolated after every prior, RF fit,
    # mask, acceptance decision and null replay has completed.
    from report_algo02_ds23 import position_error
    rows=[];summary={};fig,axes=plt.subplots(2,2,figsize=(14,8))
    for k,cohort in enumerate(('development','confirmation')):
        summary[cohort]={}
        for col,arm in enumerate(('c0','fitted_c')):
            before=[];after=[];raw=[];accepted=0;gains=[]
            for case in protocol[cohort+'_cases']:
                r=read(OUT/(case+'.json'));prior=read(OUT/(case+'_prior.json'))
                before.append(position_error(r['incumbent_arms'][arm]['endpoint_latlon']))
                after.append(position_error(r['policy_arms'][arm]['endpoint_latlon']))
                raw.append(position_error(r['arms'][arm]['endpoint_latlon']));accepted+=int(r['accepted'])
                gain=prior['selection'].get('density_gains',{}).get('disjoint_future',0.)
                gains.append(gain)
                rows.append(dict(case=case,cohort=cohort,arm=arm,prior_qualified=r['qualified'],accepted=r['accepted'],
                    original_error_km=before[-1],policy_error_km=after[-1],raw_trial_error_km=raw[-1],
                    frequency_RMS_before_hz=r['incumbent_arms'][arm]['RMS_hz'],
                    frequency_RMS_trial_hz=r['arms'][arm]['RMS_hz'],
                    disjoint_future_TLE_density_gain=gain))
            d=np.asarray(after)-before
            summary[cohort][arm]=dict(incumbent=stats(before),policy=stats(after),raw_trial=stats(raw),
                accepted=accepted,mean_and_median_improve=bool(np.mean(after)<np.mean(before) and np.median(after)<np.median(before)),
                improved_scans=int(np.sum(d< -1e-9)),worsened_scans=int(np.sum(d>1e-9)))
            ax=axes[k,col];selected=[r for r in rows if r['cohort']==cohort and r['arm']==arm]
            ax.bar(range(len(d)),1000*d,color=['#b8b8b8' if not r['accepted'] else '#348653' if v<0 else '#c45d67' for r,v in zip(selected,d)])
            ax.axhline(0,color='black',lw=.7)
            ax.set(xticks=range(len(d)),xticklabels=[r['case'].split('-')[-1] for r in selected],
                title=f'{cohort} · {arm}',xlabel='DS23 scan',ylabel='Position error change (m; negative improves)')
            ax.tick_params(axis='x',rotation=60,labelsize=7);ax.grid(axis='y',alpha=.15)
    fig.suptitle('DS23 · shared satellite phase/shape tail events\nSame marginal variances, causal TLE qualification, observations and regional search; failed-pair fallback')
    fig.tight_layout(rect=(0,0,1,.92));fig.savefig(OUT/'position_error_changes.png',dpi=175);plt.close(fig)
    primary=all(summary[c]['fitted_c']['mean_and_median_improve'] for c in summary)
    all_four=all(v['mean_and_median_improve'] for c in summary.values() for v in c.values())
    families=[r for replay in replays for r in replay['families']]
    for path,data in ((OUT/'position_comparison.csv',rows),(OUT/'family_tail_diagnostics.csv',families)):
        with path.open('w') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(data[0]),lineterminator='\n');writer.writeheader();writer.writerows(data)
    write(OUT/'disabled_coupling_replay.json',dict(replays=replays,
        maximum_RF_difference=max(abs(n['RF_difference']) for r in replays for n in r['nulls']),
        all_saved_joint_tail_endpoints_reproduced=True,no_GPS_used_for_replay=True,
        source_sha256=sha(Path(__file__))))
    write(OUT/'evaluation.json',dict(summary=summary,primary_confirmed=primary,all_c_arm_metrics_confirmed=all_four,
        count=len(cases),population=413,all_new_jobs_terminal=True,no_default_changed=True,
        mean_and_median_half_km_goal_achieved=False,geographic_reference_only_in_reporter=True,
        independent_confirmation_for_this_hypothesis_not_untouched_GPS_locations=True,
        maximum_disabled_coupling_RF_difference=max(abs(n['RF_difference']) for r in replays for n in r['nulls']),
        protocol_sha256=sha(OUT/'protocol.json'),source_sha256=sha(Path(__file__))))
    print(summary,flush=True);print('Primary confirmed',primary,'all-c confirmed',all_four,flush=True)


if __name__=='__main__':main()
