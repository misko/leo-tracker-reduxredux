"""Post-fit geographic evaluation; never imported by the RF selection driver."""

import argparse
import csv
from collections import Counter

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from evaluate_ds23_candidate_policies import metrics
from evaluate_ds23_causal_phase_location_full import capture_format
from probe_ds23_symmetric_family_selection import OUT
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT,read,write,sha


def main(out=OUT,study='symmetric'):
    out=out.resolve()
    protocol,execution=read(out/'protocol.json'),read(out/'execution.json')
    receipts=execution['receipts']
    if not execution['all_terminal'] or len(receipts)!=len(protocol['cases']) or {r['case'] for r in receipts}!=set(protocol['cases']):
        raise ValueError('every original cohort case must be terminal and represented exactly once')
    for path,digest in protocol['source_sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('frozen inference code changed')
    members={r['dataset_label']:r for r in read(ROOT/'reports/2026_10_18_ds23_post_ds22/manifest.json')['members']}
    signed=read(ROOT/'reports/2026_10_20_ds23_causal_phase_location_full/evaluation_audit.json')['evidence']
    rows=[];failures=[];bindings={}
    for receipt in sorted(receipts,key=lambda r:r['case']):
        case=receipt['case'];binding=signed[case];path=ROOT/binding['path']
        if sha(path)!=binding['sha256']:raise ValueError('signed reference source changed')
        incumbent=read(path)['policy_arms']
        old=read(ROOT/'reports/2026_10_19_algo02_ds23_full'/case/'algo02_result.json')['policy_arms']
        result=None
        if 'error' in receipt:failures.append(receipt)
        else:
            result_path=out/case/'result.json';result=read(result_path)
            if result['incumbent_arms']!=incumbent or result['baseline_arms']!=old:
                raise ValueError('reference arms changed')
            if result['GPS_used'] or result['future_TLE_used']:raise ValueError('invalid fitter inputs')
            bindings[case]=dict(path=str(result_path.relative_to(ROOT)),sha256=sha(result_path))
        chosen=result['policy_arms'] if result else incumbent
        for arm in ('c0','fitted_c'):
            selected=result.get('selected') if result else None
            predictive_choice=bool(result and result['accepted'] and study=='family_prediction')
            rows.append(dict(case=case,arm=arm,format=capture_format(members[case]['recording_format']),
                model=(selected['covariance']+'_'+selected['name'] if selected else
                       'predictively_qualified_fine' if predictive_choice else 'signed_incumbent'),
                original_error_km=position_error(old[arm]['endpoint_latlon']),
                incumbent_error_km=position_error(incumbent[arm]['endpoint_latlon']),
                policy_error_km=position_error(chosen[arm]['endpoint_latlon']),
                RF_gain=incumbent[arm]['negative_twice_elbo']-chosen[arm]['negative_twice_elbo'],
                coded_RF_gain=(selected['RF_coded_gains'][arm] if selected else 0.),
                conditional_predictive_gain=sum(r['gain'] for r in result['gains'][arm]) if result and study=='family_prediction' else 0.,
                RMS_before_hz=incumbent[arm]['RMS_hz'],RMS_after_hz=chosen[arm]['RMS_hz'],
                execution_failed=result is None))
    summary={}
    for group in ('all','fast','adaptive'):
        summary[group]={}
        for arm in ('c0','fitted_c'):
            subset=[r for r in rows if r['arm']==arm and (group=='all' or r['format']==group)]
            if not subset:continue
            summary[group][arm]={name:metrics([r[name+'_error_km'] for r in subset])
                                 for name in ('original','incumbent','policy')}
            summary[group][arm]['choices']=dict(Counter(r['model'] for r in subset))
    positive=not failures and all(summary['all'][a]['policy'][m]<summary['all'][a][reference][m]
        for a in ('c0','fitted_c') for m in ('mean_km','median_km') for reference in ('original','incumbent'))
    write(out/'evaluation.json',dict(study=study,summary=summary,failures=failures,positive_development=bool(positive),
        independent_confirmation_not_yet_run=True,goal_achieved=False,full_413_population_still_required=True,
        GPS_used_only_in_reporter=True,new_location_generalization_not_tested=True,evidence=bindings))
    with (out/'positions.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        chosen=[r for r in rows if r['arm']==arm]
        for name,label,color in [('original','Original ALGO02','#999999'),('incumbent','Published signed prior','#317bb2'),('policy','Symmetric family search','#a363a8')]:
            values=np.sort([r[name+'_error_km'] for r in chosen])
            if name=='policy' and study=='family_prediction':label='Family-predictive selection'
            ax.step(np.r_[0,values],np.r_[0,np.arange(1,len(values)+1)/len(protocol['cases'])],where='post',label=label,color=color)
        ax.axvline(.5,color='black',ls=':');ax.set(title=arm,xlabel='Position error (km)',ylabel='Fraction of all cohort scans',ylim=(0,1.02))
        ax.grid(alpha=.15);ax.legend(fontsize=8)
    fig.suptitle(f'DS23 fixed 20-scan development cohort · {study}\nAll failed or rejected proposals retain the signed incumbent')
    fig.tight_layout(rect=(0,0,1,.9));fig.savefig(out/'position_error_distribution.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        chosen=[r for r in rows if r['arm']==arm]
        for format,color in [('fast','#267b44'),('adaptive','#9659ad')]:
            selected=[r for r in chosen if r['format']==format]
            ax.scatter([r['RF_gain'] for r in selected],
                [r['incumbent_error_km']-r['policy_error_km'] for r in selected],label=format,color=color)
        ax.axhline(0,color='gray',lw=.8);ax.axvline(0,color='gray',lw=.8)
        ax.set(title=arm,xlabel='Full RF bound gain',ylabel='Position error reduction versus signed incumbent (km)')
        ax.legend();ax.grid(alpha=.15)
    fig.suptitle('Better frequency evidence is not necessarily better localization')
    fig.tight_layout(rect=(0,0,1,.93));fig.savefig(out/'RF_gain_vs_position_change.png',dpi=170);plt.close(fig)
    print('Positive development:',positive,'errors',len(failures),flush=True)
    print(summary,flush=True)


if __name__=='__main__':
    from pathlib import Path
    parser=argparse.ArgumentParser();parser.add_argument('--run-dir',type=Path,default=OUT)
    parser.add_argument('--study',choices=('symmetric','family_prediction'),default='symmetric')
    args=parser.parse_args();main(args.run_dir,args.study)
