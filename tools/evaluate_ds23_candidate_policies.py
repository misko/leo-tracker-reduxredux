"""Geographic reporting for frozen RF-only receiver/prior selection studies."""

import argparse
import csv
from collections import Counter

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT, read, write, sha
from evaluate_ds23_causal_phase_location_full import capture_format

SOURCE = ROOT/'reports/2026_10_19_algo02_ds23_full'


def metrics(values):
    a = np.asarray(values, float)
    return dict(count=len(a), mean_km=float(a.mean()), median_km=float(np.median(a)),
        p90_km=float(np.quantile(a,.9)), maximum_km=float(a.max()), below_half_km=int(np.sum(a<=.5)))


def evaluate(study, run_dir=None):
    defaults=dict(receiver='2026_10_20_ds23_receiver_family_search',
                  prior='2026_10_20_ds23_prior_evidence_selection',
                  predictive='2026_10_20_ds23_hierarchical_predictive')
    out = run_dir if run_dir is not None else ROOT/'reports'/defaults[study]
    out = out.resolve()
    protocol, execution = read(out/'protocol.json'), read(out/'execution.json')
    receipts = execution['results'] if study=='prior' else execution['receipts']
    if not execution['all_terminal'] or len(receipts)!=len(protocol['cases']):
        raise ValueError('complete cohort required before geographic evaluation')
    if {r['case'] for r in receipts} != set(protocol['cases']):
        raise ValueError('missing or duplicate cohort members')
    for path, digest in protocol['source_sha256'].items():
        if sha(ROOT/path)!=digest:
            raise ValueError('frozen experiment source changed')
    members = {r['dataset_label']:r for r in read(ROOT/'reports/2026_10_18_ds23_post_ds22/manifest.json')['members']}
    location = read(ROOT/'reports/2026_10_20_ds23_causal_phase_location_full/evaluation_audit.json')['evidence']
    rows, failures, artifacts = [], [], {}
    for receipt in receipts:
        case=receipt['case']
        old = read(SOURCE/case/'algo02_result.json')
        baseline = old['policy_arms']
        path = out/(case+'.json') if study=='prior' else out/case/'result.json'
        if 'error' in receipt:
            failures.append(receipt)
            result=None
            chosen=baseline
        else:
            result=read(path)
            if result['baseline_sha256'] != sha(SOURCE/case/'algo02_result.json'):
                raise ValueError('baseline authority changed')
            if result['GPS_used'] or result['future_TLE_used']:
                raise ValueError('invalid inference input')
            chosen=result['policy_arms']
            artifacts[case]=dict(path=str(path.relative_to(ROOT)), sha256=sha(path))
        signed=read(ROOT/location[case]['path'])['policy_arms']
        for arm in ('c0','fitted_c'):
            a,b=baseline[arm],chosen[arm]
            choice=(result['choice']['model'] if study=='prior' else
                    result.get('policy_name','receiver_search' if result['accepted'] else 'original')) if result else 'original'
            rows.append(dict(case=case, arm=arm, format=capture_format(members[case]['recording_format']),
                model=choice, remaining=case in protocol.get('remaining340', []),
                baseline_error_km=position_error(a['endpoint_latlon']),
                signed_error_km=position_error(signed[arm]['endpoint_latlon']),
                policy_error_km=position_error(b['endpoint_latlon']),
                baseline_RF_loss=a['negative_twice_elbo'], policy_RF_loss=b['negative_twice_elbo'],
                baseline_RMS_hz=a['RMS_hz'], policy_RMS_hz=b['RMS_hz'], execution_failed=result is None))
    groups=dict(all=rows,fast=[r for r in rows if r['format']=='fast'],adaptive=[r for r in rows if r['format']=='adaptive'])
    if study=='prior':
        groups['remaining340']=[r for r in rows if r['remaining']]
    summary={}
    for group, selected in groups.items():
        summary[group]={}
        for arm in ('c0','fitted_c'):
            subset=[r for r in selected if r['arm']==arm]
            if not subset:
                continue
            summary[group][arm]={name:metrics([r[column] for r in subset]) for name,column in
                [('original','baseline_error_km'),('signed','signed_error_km'),('policy','policy_error_km')]}
            summary[group][arm]['choices']=dict(Counter(r['model'] for r in subset))
    compared=('all','remaining340') if study=='prior' else ('all',)
    positive=not failures and all(summary[g][a]['policy'][m]<summary[g][a][reference][m]
        for g in compared for a in ('c0','fitted_c') for reference in ('original','signed') for m in ('mean_km','median_km'))
    write(out/'evaluation.json',dict(study=study,summary=summary,failures=failures,
        positive_vs_original_and_published_signed_prior=bool(positive),GPS_only_in_reporter=True,
        unavailable_original_population=protocol.get('unavailable',[]),
        goal_met=False,full_413_mean_and_median_half_km_still_required=True,
        same_site_recording_transfer_not_external_location_validation=True))
    write(out/'evaluation_audit.json',dict(evidence=artifacts,source_sha256=protocol['source_sha256']))
    with (out/'positions.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    denom=len(protocol['population']) if study=='prior' else len(protocol['cases'])
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        selected=[r for r in rows if r['arm']==arm]
        for column,label in [('baseline_error_km','Original ALGO02'),('signed_error_km','Published signed prior'),('policy_error_km','New RF-selected policy')]:
            values=np.sort([r[column] for r in selected])
            ax.step(np.r_[0,values],np.r_[0,np.arange(1,len(values)+1)/denom],where='post',label=label)
        ax.axvline(.5,color='gray',ls=':',lw=.8)
        ax.set(title=arm,xlabel='Position error (km)',ylabel='Fraction of cohort population',ylim=(0,1.02))
        ax.grid(alpha=.15);ax.legend(fontsize=8)
    fig.suptitle(f'DS23 {study} policy · {len(protocol["cases"])} recordings\nAll failures retain the incumbent; no GPS-selected deletions')
    fig.tight_layout(rect=(0,0,1,.9));fig.savefig(out/'position_error_distribution.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for capture,color in [('fast','#267b44'),('adaptive','#9659ad')]:
            chosen=[r for r in rows if r['arm']==arm and r['format']==capture]
            ax.scatter([r['baseline_RF_loss']-r['policy_RF_loss'] for r in chosen],
                       [r['baseline_error_km']-r['policy_error_km'] for r in chosen],s=18,alpha=.6,color=color,label=capture)
        ax.axhline(0,color='gray',lw=.8);ax.axvline(0,color='gray',lw=.8)
        ax.set(title=arm,xlabel='RF bound improvement (positive is better)',ylabel='Position error reduction (km)')
        ax.grid(alpha=.15);ax.legend()
    fig.suptitle('Frequency evidence and position accuracy are different outcomes')
    fig.tight_layout(rect=(0,0,1,.93));fig.savefig(out/'RF_gain_vs_position_change.png',dpi=170);plt.close(fig)
    print('Positive criterion:',positive,'errors',len(failures),flush=True)
    print(summary,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--study',choices=('receiver','prior','predictive'),required=True)
    from pathlib import Path
    parser.add_argument('--run-dir',type=Path)
    args=parser.parse_args()
    evaluate(args.study,args.run_dir)
