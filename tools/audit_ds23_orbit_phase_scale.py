"""Replay causal scale qualification; reject unsupported policies before RF runs."""

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_continuous_forecast import arrays
from ds23_family_orbit_tail import joint_student_cost
from ds23_orbit_phase_scale import qualify
from learn_ds23_causal_phase_forecast import distribution_cost
from probe_ds23_orbit_phase_scale import OUT, prepare
from probe_ds23_symmetric_family_selection import bound_incumbent
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT, read, write, sha


def verify(case):
    path=OUT/(case+'_scale.json'); saved=read(path)
    history_path=SOURCE/'causal_phase_history'/(case+'.json')
    forecast_path=history_path.with_name(case+'_forecast.json')
    if sha(history_path)!=saved['history_sha256'] or sha(forecast_path)!=saved['forecast_sha256']:
        raise ValueError('TLE qualification input changed')
    old_path=SOURCE/case/'algo02_result.json'
    if sha(old_path)!=saved['old_result_sha256']:
        raise ValueError('baseline changed')
    signed,binding=bound_incumbent(case)
    enabled=bool(signed['accepted'] and signed['selection']['qualified'])
    bias=dict(kind=signed['selection']['kind'],coefficient=signed['selection']['coefficient']) if enabled else None
    if binding!=saved['incumbent_binding'] or enabled!=saved['bias_enabled'] or bias!=saved['full_bias']:
        raise ValueError('incumbent bias conditioning changed')
    result=qualify(read(history_path),read(forecast_path),saved['baseline_model'],enabled,bias)
    if result!=saved['selection']:
        raise ValueError('physical-scale fit or qualification did not replay exactly')
    return dict(case=case,qualified=result['qualified'],proposal_sha256=sha(path),no_GPS_used=True)


def shared_scale_diagnostic(cases):
    """No fit: compare one versus independent Gamma scales at each event."""
    results=[]
    for case in cases:
        saved=read(OUT/(case+'_scale.json'))
        forecast=read(SOURCE/'causal_phase_history'/(case+'_forecast.json'))
        model=forecast['prefix_distribution']
        if model['nu'] is None:
            continue
        for name,rows in (
                ('prefix',[r for r in forecast['transitions'] if r['validation_time_ns']<=forecast['temporal_split_boundary_ns']]),
                ('future',[r for r in forecast['transitions'] if r['validation_time_ns']>forecast['temporal_split_boundary_ns']])):
            # Keep this unconditioned baseline mean identical in both densities.
            a=arrays(rows,model)
            z=(a['target']-np.clip(model['shrinkage']*a['unit'],-a['limit'],a['limit']))/(a['sigma']*model['multiplier'])
            groups=defaultdict(list)
            for k,row in enumerate(rows):
                groups[row['validation_time_ns']].append(k)
            values=[]
            for event,indices in groups.items():
                if len(indices)<2:
                    continue
                v=z[indices]
                old=float(distribution_cost(v,np.ones(len(v)),1.,model['nu']).sum())
                new=float(joint_student_cost(v[None,:],model['nu'])[0])
                values.append(dict(event_utc_ns=event,dimensions=len(v),independent_cost=old,
                                   common_cost=new,gain=old-new))
            results.append(dict(case=case,partition=name,events=values,
                total_gain=sum(v['gain'] for v in values)))
    write(OUT/'shared_scale_pilot_diagnostic.json',dict(rows=results,
        marginal_variances_and_Student_degrees_preserved=True,
        no_current_RF_or_GPS_or_future_TLE_used=True,
        unconditioned_baseline_mean_identical_in_both_models=True,
        diagnostic_no_position_policy_qualification=True,
        source_sha256=sha(ROOT/'tools/audit_ds23_orbit_phase_scale.py')))


def main():
    protocol=prepare();cases=protocol['development_cases']+protocol['confirmation_cases']
    with ProcessPoolExecutor(max_workers=16) as pool:
        verified=list(pool.map(verify,cases))
    if any(r['qualified'] for r in verified):
        raise ValueError('a qualified position experiment remains; do not finalize as all-rejected')
    rows=[]
    for case in cases:
        selection=read(OUT/(case+'_scale.json'))['selection']
        for split,result in selection['validation'].items():
            rows.append(dict(case=case,cohort='development' if case in protocol['development_cases'] else 'confirmation',
                partition=split,penalty=selection['penalty'],**{k:v for k,v in result.items() if k!='scores'}))
    with (OUT/'historical_validation.csv').open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for ax,partition in zip(axes,('future','disjoint_future')):
        selected=[r for r in rows if r['partition']==partition]
        for cohort,color in (('development','#397cb1'),('confirmation','#ce7838')):
            chosen=[r for r in selected if r['cohort']==cohort]
            ax.scatter([r['gain_vs_scalar'] for r in chosen],[r['gain_vs_baseline'] for r in chosen],
                c=color,label=cohort,alpha=.75)
        penalties=[r['penalty'] for r in selected]
        ax.axvspan(min(penalties),max(penalties),alpha=.1,color='gray')
        ax.axhspan(min(penalties),max(penalties),alpha=.1,color='gray')
        ax.axvline(0,color='gray',lw=.6);ax.axhline(0,color='gray',lw=.6)
        ax.set(title=partition,xlabel='Density gain over scalar-only control',ylabel='Density gain over existing model')
        ax.grid(alpha=.15);ax.legend(fontsize=8)
    fig.suptitle('Physical-element-conditioned phase uncertainty: 0 / 40 histories qualify\n'
        'Both gains must exceed each scan’s 3 log N penalty (gray bands), in BOTH panels')
    fig.tight_layout(rect=(0,0,1,.9));fig.savefig(OUT/'historical_qualification.png',dpi=175);plt.close(fig)
    shared_scale_diagnostic(protocol['pilot_cases'])
    write(OUT/'qualification_audit.json',dict(all_terminal=True,qualified_histories=0,
        verified_count=len(verified),receipts=verified,errors=[],all_qualification_replays_exact=True,
        position_jobs_required=0,position_fits_performed=0,policy_unchanged=True,
        no_position_accuracy_claim=True,goal_achieved=False,goal_population=413,
        source_sha256=sha(ROOT/'tools/audit_ds23_orbit_phase_scale.py'),
        protocol_sha256=sha(OUT/'protocol.json')))
    print('Exact causal qualification replays',len(verified),'qualified 0; no position fits justified',flush=True)


if __name__=='__main__':
    main()
