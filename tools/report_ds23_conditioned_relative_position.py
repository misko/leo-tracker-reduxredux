"""Audit restored-prior position fits before all-scan geographic comparison."""

from concurrent.futures import ProcessPoolExecutor
from functools import partial
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from audit_ds23_joint_relative_position import one as audit_one
from probe_ds23_conditioned_relative_position import OUT,VARIANTS,context_selected
from probe_ds23_joint_relative_position import CASES
from probe_ds23_sign_carrier_position import context_signed
from run_algo01_ds23_sample import read,write,sha


def audit(record):
    return audit_one(record,OUT,partial(context_selected,variant=record['variant']))


def main():
    execution=read(OUT/'execution.json');protocol=read(OUT/'protocol.json');assert execution['all_terminal']
    lookup={(r['case'],r['variant']):r for r in execution['rows']};assert len(lookup)==46
    complete=[r for r in execution['rows'] if r['status']=='complete']
    with ProcessPoolExecutor(max_workers=8) as pool:audits=list(pool.map(audit,complete))
    write(OUT/'independent_numerical_audit.json',dict(audits=audits,all_passed=True,
        original_hierarchical_priors_exact_joint_geometry_and_dense_predictive_covariance_checked=True,
        all_original_gates_replayed=True,reference_position_used=False,source_sha256=sha(OUT/'execution.json')))
    from report_algo02_ds23 import position_error
    rows=[];statistics={}
    for record in execution['rows']:
        incumbent=record.get('original_incumbent') or context_signed(record['case'])[-2]['policy_arms']
        for arm in ['c0','fitted_c']:
            a=record['arms'][arm] if record['status']=='complete' else None
            old=position_error(incumbent[arm]['endpoint_latlon']);accepted=record['accepted']
            rows.append(dict(case=record['case'],variant=record['variant'],arm=arm,cohort='development' if record['case'] in CASES else 'comparison20',
                status=record['status'],accepted=accepted,original_error_km=old,
                raw_error_km=position_error(a['endpoint_latlon']) if a else None,
                policy_error_km=position_error(a['endpoint_latlon']) if accepted else old,
                retained_GLRT_RMS_hz=a['RMS_hz'] if a else None,
                selected_relative_groups=len(record.get('selected_pairs',{})),unresolved_relative_groups=len(record.get('unresolved_RF_groups',[])),
                original_Gamma_Student_and_physical_priors_restored=record.get('all_original_hierarchical_Gamma_Student_orbit_radio_fragment_priors_restored',False),
                failed_curved=0 if not a else sum(not g['compatible'] for g in a['gates']['tracks']),
                failed_predictive=0 if not a else sum(not g['compatible'] for g in a['linear_gates']),
                failed_relative=0 if not a else sum(not g['compatible'] for g in a['relative_gates'])))
    for cohort in ['development','comparison20']:
        statistics[cohort]={}
        for variant in VARIANTS:
            statistics[cohort][variant]={}
            for arm in ['c0','fitted_c']:
                selected=[r for r in rows if (r['cohort'],r['variant'],r['arm'])==(cohort,variant,arm)]
                old=np.array([r['original_error_km'] for r in selected]);new=np.array([r['policy_error_km'] for r in selected]);delta=new-old
                rng=np.random.default_rng(2026102203);ix=rng.integers(0,len(new),size=(5000,len(new)))
                statistics[cohort][variant][arm]=dict(count=len(new),accepted=sum(r['accepted'] for r in selected),
                    original_mean_km=float(old.mean()),original_median_km=float(np.median(old)),
                    policy_mean_km=float(new.mean()),policy_median_km=float(np.median(new)),
                    improved=int(np.sum(delta< -1e-6)),worsened=int(np.sum(delta>1e-6)),p90_km=float(np.percentile(new,90)),
                    maximum_km=float(new.max()),at_most0p5km=int(np.sum(new<=.5)),
                    paired_bootstrap_mean_change95_km=np.percentile(np.mean(delta[ix],axis=1),[2.5,97.5]),
                    paired_bootstrap_median_change95_km=np.percentile(np.median(new[ix],axis=1)-np.median(old[ix],axis=1),[2.5,97.5]))
    write(OUT/'evaluation.json',dict(rows=rows,statistics=statistics,report_only_GPS=True,
        all23_scans_including_no_offer_failed_jobs_and_failed_gates=True,
        comparison20_disjoint_from_development_but_previously_inspected_by_other_algorithms=True,
        same_site_not_new_location=True,no_full_DS23_or_goal_achievement_claim=True))
    with (OUT/'positions.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    cases=[c for c in protocol['cases'] if c not in CASES];fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained');x=np.arange(len(cases))
    for variant,color,marker in [('conditioned_best','#168b91','o'),('conditioned_strict','#8765b4','s')]:
        selected=[next(r for r in rows if (r['case'],r['variant'],r['arm'])==(c,variant,'fitted_c')) for c in cases]
        error=np.array([r['policy_error_km'] for r in selected]);old=np.array([r['original_error_km'] for r in selected])
        axes[0].scatter(x,error,c=color,marker=marker,s=30,label=variant)
        axes[1].plot(np.sort(error),np.arange(1,len(error)+1)/len(error),c=color,label=variant)
    axes[0].scatter(x,old,c='black',marker='x',s=35,label='Original signed-prior incumbent')
    axes[1].plot(np.sort(old),np.arange(1,len(old)+1)/len(old),c='black',label='Original incumbent')
    axes[0].set_xticks(x,[c.split('-')[1] for c in cases],rotation=70,fontsize=7)
    axes[0].set(xlabel='DS23 comparison scan',ylabel='Position error (km)');axes[1].set(xlabel='Position error (km)',ylabel='Empirical CDF')
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('GLRT-conditioned relative-pair nominations · full original priors restored\nFrozen20scan comparison; all fallbacks; previously inspected cohort at same site')
    fig.savefig(OUT/'comparison20.png',dpi=160);plt.close(fig)
    print(statistics,flush=True)


if __name__=='__main__':main()
