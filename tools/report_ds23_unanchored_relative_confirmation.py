"""Audit all frozen confirmation fits before geographic evaluation."""

from concurrent.futures import ProcessPoolExecutor
from functools import partial
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from audit_ds23_unanchored_relative_position import one as audit_one
from confirm_ds23_unanchored_relative_position import OUT
from probe_ds23_unanchored_relative_position import VARIANTS
from run_algo01_ds23_sample import read,write


def main():
    execution=read(OUT/'execution.json');protocol=read(OUT/'protocol.json');assert execution['all_terminal']
    expected={(c,v[0]) for c in protocol['cases'] for v in VARIANTS}
    lookup={(r['case'],r['variant']):r for r in execution['rows']};assert set(lookup)==expected and len(lookup)==80
    complete=[r for r in execution['rows'] if r['status']=='complete']
    assert all(r['status'] in ['complete','no_offer','failed'] for r in execution['rows'])
    with ProcessPoolExecutor(max_workers=8) as pool:audits=list(pool.map(partial(audit_one,output_dir=OUT),complete))
    assert all(a['causal_element_epoch_and_collection_checked'] for a in audits)
    write(OUT/'independent_numerical_audit.json',dict(audits=audits,all_terminal=True,endpoint_replays=len(audits),
        frequency_geometry_and_physical_mode_gradients_independently_replayed=True,
        report_only_GPS_not_read_yet=True))
    # Selection uses only residual gates and normalized relative-data evidence.
    selected={};evidence={}
    for case in protocol['cases']:
        options=[lookup[case,v[0]] for v in VARIANTS if lookup[case,v[0]].get('accepted')]
        best=min(options,key=lambda r:r['negative_twice_elbo']) if options else None
        evidence[case]=best
        selected[case]=dict(variant=None if best is None else best['variant'],
            objective=None if best is None else best['negative_twice_elbo'],RF_only_no_GPS=True)
    write(OUT/'evidence_selection.json',selected)
    from report_algo02_ds23 import position_error
    policies=[v[0] for v in VARIANTS]+['evidence_selected'];rows=[];statistics={}
    for policy in policies:
        for case in protocol['cases']:
            record=evidence[case] if policy=='evidence_selected' else lookup[case,policy]
            incumbent=lookup[case,VARIANTS[0][0]]['original_signed_incumbent']
            accepted=record is not None and record.get('accepted',False)
            for arm in ['c0','fitted_c']:
                old=position_error(incumbent[arm]['endpoint_latlon'])
                value=position_error(record['endpoint_latlon']) if accepted else old
                rows.append(dict(case=case,policy=policy,arm=arm,accepted=bool(accepted),
                    selected_variant=None if record is None else record['variant'],incumbent_error_km=old,
                    policy_error_km=value,raw_error_km=position_error(record['endpoint_latlon']) if record and record['status']=='complete' else None,
                    frequency_RMS_hz=record.get('RMS_hz') if record else None,
                    status='incumbent_fallback' if not accepted else 'accepted',
                    relative_observations=0 if not record else record.get('relative_observations',0)))
        statistics[policy]={}
        for arm in ['c0','fitted_c']:
            subset=[r for r in rows if r['policy']==policy and r['arm']==arm]
            old=np.array([r['incumbent_error_km'] for r in subset]);new=np.array([r['policy_error_km'] for r in subset]);delta=new-old
            rng=np.random.default_rng(2026102201);indices=rng.integers(0,len(new),size=(5000,len(new)))
            mean_change=np.mean(delta[indices],axis=1)
            median_change=np.median(new[indices],axis=1)-np.median(old[indices],axis=1)
            statistics[policy][arm]=dict(count=len(new),accepted=sum(r['accepted'] for r in subset),
                incumbent_mean_km=float(old.mean()),incumbent_median_km=float(np.median(old)),
                policy_mean_km=float(new.mean()),policy_median_km=float(np.median(new)),
                improved=int(np.sum(delta< -1e-6)),worsened=int(np.sum(delta>1e-6)),
                p90_km=float(np.percentile(new,90)),maximum_km=float(new.max()),
                at_most0p5km=int(np.sum(new<=.5)),paired_bootstrap_mean_change95_km=np.percentile(mean_change,[2.5,97.5]),
                paired_bootstrap_median_change95_km=np.percentile(median_change,[2.5,97.5]))
    write(OUT/'evaluation.json',dict(rows=rows,statistics=statistics,all_terminal=True,
        all20_scans_including_no_offer_and_failed_gates=True,scan_disjoint_same_site_not_new_location=True,
        default_frozen_before_confirmation_error_evaluation=protocol['prespecified_default'],
        no_full_DS23_or_goal_achievement_claim=True))
    with (OUT/'positions.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(13,5.1));cases=protocol['cases'];x=np.arange(len(cases))
    for policy,color in [('physical_bias424','#168b91'),('evidence_selected','#8765b4')]:
        subset=[next(r for r in rows if r['case']==c and r['policy']==policy and r['arm']=='fitted_c') for c in cases]
        error=np.array([r['policy_error_km'] for r in subset]);old=np.array([r['incumbent_error_km'] for r in subset])
        axes[0].scatter(x,error,label=policy,color=color,s=28)
        axes[1].plot(np.sort(error),np.arange(1,len(error)+1)/len(error),label=policy,color=color)
    axes[0].scatter(x,old,color='black',marker='x',label='Original signed-prior incumbent')
    axes[1].plot(np.sort(old),np.arange(1,len(old)+1)/len(old),color='black',label='Original incumbent')
    axes[0].set_xticks(x,[c.split('-')[1] for c in cases],rotation=70,fontsize=7)
    axes[0].set(xlabel='DS23 confirmation scan',ylabel='Position error (km)');axes[1].set(xlabel='Position error (km)',ylabel='Empirical CDF')
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Unanchored relative-Doppler · frozen20-scan confirmation; all fallbacks included')
    fig.tight_layout();fig.savefig(OUT/'confirmation_comparison.png',dpi=160);plt.close(fig)
    print(statistics,flush=True)


if __name__=='__main__':main()
