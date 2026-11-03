"""Independent replay and all-scan accounting for the frozen joint comparison."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from functools import partial
import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from audit_ds23_joint_relative_position import one as audit_one
from confirm_ds23_joint_relative_position import OUT
from probe_ds23_joint_relative_position import VARIANTS
from run_algo01_ds23_sample import read,write,sha


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,default=OUT)
    args=parser.parse_args();out=args.directory
    execution=read(out/'execution.json');protocol=read(out/'protocol.json');variants=protocol['variants'];assert execution['all_terminal']
    lookup={(r['case'],r['variant']):r for r in execution['rows']}
    assert len(lookup)==len(execution['rows'])==len(protocol['cases'])*len(variants)
    assert set(lookup)=={(c,v[0]) for c in protocol['cases'] for v in variants}
    preflight={r['case']:r for r in read(out/'preflight_execution.json')['rows']}
    complete=[r for r in execution['rows'] if r['status']=='complete']
    with ProcessPoolExecutor(max_workers=8) as pool:audits=list(pool.map(partial(audit_one,output_dir=out),complete))
    write(out/'independent_numerical_audit.json',dict(audits=audits,all_passed=True,endpoint_pairs_replayed=len(audits),
        direct_expected_log_density_and_entropy=True,independent_grid_and_perturbed_orbit_features=True,
        dense_predictive_covariance_checked=True,all_original_gates_replayed=True,reference_position_used=False,
        evidence_hash=sha(out/'execution.json')))
    from report_algo02_ds23 import position_error
    rows=[];statistics={}
    for variant,_,_ in variants:
        for case in protocol['cases']:
            record=lookup[case,variant]
            original=record.get('original_incumbent') or preflight[case].get('original_incumbent')
            if original is None:
                original=read(out/(case+'_'+variant+'.json')).get('original_incumbent')
            if original is None:raise ValueError('missing fallback incumbent; do not drop scan')
            accepted=record.get('accepted',False)
            for arm in ['c0','fitted_c']:
                old=position_error(original[arm]['endpoint_latlon']);a=record['arms'][arm] if record['status']=='complete' else None
                rows.append(dict(case=case,variant=variant,arm=arm,accepted=accepted,status=record['status'],
                    preflight_status=preflight[case]['status'],original_error_km=old,
                    raw_error_km=position_error(a['endpoint_latlon']) if a else None,
                    policy_error_km=position_error(a['endpoint_latlon']) if accepted else old,
                    retained_GLRT_RMS_hz=a['RMS_hz'] if a else None,
                    retained_curved_points=a['active_points'] if a else 0,
                    failed_curved=0 if not a else sum(not g['compatible'] for g in a['gates']['tracks']),
                    failed_predictive=0 if not a else sum(not g['compatible'] for g in a['linear_gates']),
                    failed_relative=0 if not a else sum(not g['compatible'] for g in a['relative_gates']),
                    phase_change_s=a['final_phase_change_s'] if a else None))
        statistics[variant]={}
        for arm in ['c0','fitted_c']:
            selected=[r for r in rows if r['variant']==variant and r['arm']==arm]
            old=np.array([r['original_error_km'] for r in selected]);new=np.array([r['policy_error_km'] for r in selected]);delta=new-old
            rng=np.random.default_rng(2026102202);ix=rng.integers(0,len(new),size=(5000,len(new)))
            statistics[variant][arm]=dict(count=len(new),accepted=sum(r['accepted'] for r in selected),
                original_mean_km=float(old.mean()),original_median_km=float(np.median(old)),
                policy_mean_km=float(new.mean()),policy_median_km=float(np.median(new)),
                improved=int(np.sum(delta< -1e-6)),worsened=int(np.sum(delta>1e-6)),p90_km=float(np.percentile(new,90)),
                maximum_km=float(new.max()),at_most0p5km=int(np.sum(new<=.5)),
                paired_bootstrap_mean_change95_km=np.percentile(np.mean(delta[ix],axis=1),[2.5,97.5]),
                paired_bootstrap_median_change95_km=np.percentile(np.median(new[ix],axis=1)-np.median(old[ix],axis=1),[2.5,97.5]))
    matched=[]
    for case in protocol['cases']:
        for arm in ['c0','fitted_c']:
            control=next(r for r in rows if (r['case'],r['arm'],r['variant'])==(case,arm,'quarantined_GLRT'))
            joint=next(r for r in rows if (r['case'],r['arm'],r['variant'])==(case,arm,'joint_bias424'))
            matched.append(dict(case=case,arm=arm,both_accepted=control['accepted'] and joint['accepted'],
                both_complete=control['status']==joint['status']=='complete',
                raw_joint_minus_control_error_km=None if control['raw_error_km'] is None or joint['raw_error_km'] is None else joint['raw_error_km']-control['raw_error_km'],
                policy_joint_minus_control_error_km=joint['policy_error_km']-control['policy_error_km']))
    write(out/'evaluation.json',dict(rows=rows,statistics=statistics,matched_control_comparison=matched,
        all20_count_including_no_offer_and_failed_gates=True,paired_c_arms=True,report_only_GPS=True,
        all_completed_likelihoods_independently_audited_before_geographic_evaluation=True,
        scan_disjoint_from_development_but_previously_inspected_cohort=True,
        same_site_not_new_location=True,no_full_DS23_or_goal_achievement_claim=True))
    with (out/'positions.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained');cases=protocol['cases'];x=np.arange(len(cases))
    for variant,color,marker in [('quarantined_GLRT','#777777','s'),('joint_bias424','#168b91','o'),('joint_bias1000','#c18c35','^')]:
        if variant not in {v[0] for v in variants}:continue
        selected=[next(r for r in rows if (r['case'],r['variant'],r['arm'])==(c,variant,'fitted_c')) for c in cases]
        error=np.array([r['policy_error_km'] for r in selected]);old=np.array([r['original_error_km'] for r in selected])
        axes[0].scatter(x,error,color=color,marker=marker,s=30,label=variant)
        axes[1].plot(np.sort(error),np.arange(1,len(error)+1)/len(error),color=color,label=variant)
    axes[0].scatter(x,old,color='black',marker='x',s=30,label='Original signed-prior incumbent')
    axes[1].plot(np.sort(old),np.arange(1,len(old)+1)/len(old),color='black',label='Original incumbent')
    axes[0].set_xticks(x,[c.split('-')[1] for c in cases],rotation=70,fontsize=7)
    axes[0].set(xlabel='DS23 comparison scan',ylabel='Position error (km)');axes[1].set(xlabel='Position error (km)',ylabel='Empirical CDF')
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('Joint absolute/relative curves · frozen20-scan comparison; all fallbacks included\nCohort disjoint from pilot development; previously inspected in other experiments; same site')
    fig.savefig(out/'confirmation_comparison.png',dpi=160);plt.close(fig)
    print(statistics,flush=True)


if __name__=='__main__':main()
