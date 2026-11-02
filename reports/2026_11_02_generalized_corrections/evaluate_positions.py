"""Postdecision geographic reporting only; never called by inference workers."""
from collections import Counter
import argparse
import csv
import hashlib
import json
from pathlib import Path
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from prototype_dsx01_continuous_position import latlon

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent/'2026_11_02_family_reliability/population/positions.csv'
SITE = (37.849061591561885, -122.48574968092912)
METHODS = ['ALGO07', 'A', 'A+B', 'A+B+C']
ARMS = ['c0', 'fitted_c']
COHORTS = ['DS24', 'DS26', 'DS27', 'DS28', 'FRSH']
COLORS = dict(zip(METHODS, ['#555555', '#277da8', '#e58b30', '#3a9a68']))
STYLES = dict(zip(METHODS, ['-', ':', '-', '--']))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def error_m(x):
    site = np.deg2rad(SITE)
    position = np.deg2rad(latlon(x))
    h = np.sin((position[0]-site[0])/2)**2 + np.cos(site[0])*np.cos(position[0])*np.sin((position[1]-site[1])/2)**2
    return float(6371008.8*2*np.arcsin(np.sqrt(np.clip(h,0,1))))


def csv_write(path, rows):
    with path.open('w') as stream:
        writer=csv.DictWriter(stream,rows[0].keys()); writer.writeheader();writer.writerows(rows)


def metrics(rows):
    errors=np.asarray([r['error_m'] for r in rows])
    delta=np.asarray([r['change_m'] for r in rows])
    return dict(count=len(rows),mean_m=float(errors.mean()),median_m=float(np.median(errors)),
        p90_m=float(np.percentile(errors,90)),p95_m=float(np.percentile(errors,95)),max_m=float(errors.max()),
        below_500m=int(np.sum(errors<500)),below_500m_percent=float(100*np.mean(errors<500)),
        improved_over50m=int(np.sum(delta < -50)),regressed_over50m=int(np.sum(delta>50)),
        maximum_regression_m=float(max(0,delta.max())),maximum_improvement_m=float(max(0,-delta.min())),
        policy_stage_accepted=sum(r['stage_accepted'] for r in rows),
        selected_new_endpoint=sum(r['output_source']!='exact_saved_ALGO07' for r in rows),
        associated_points=sum(r['associated_points'] for r in rows))


def main(results_path, audit_path):
    results=json.loads(results_path.read_text())
    assert results['workers_joined'] and results['available']==205
    assert all(r['status']!='running' for r in results['rows'])
    audit=json.loads(audit_path.read_text())
    assert audit['status']=='passed' and audit['results_sha256']==sha(results_path)
    # Bind reporting to the completed, immutable RF ledger before reading labels.
    seal=dict(created_utc_ns=time.time_ns(),results_sha256=sha(results_path),
        execution_protocol_sha256=sha(ROOT/'execution_protocol.json'),
        independent_receipt_audit_sha256=sha(audit_path),
        all_workers_joined=True,position_label_source=str(OLD),position_label_source_sha256=sha(OLD),
        purpose='Postdecision evaluation only; candidate policies and RF decisions already frozen')
    (ROOT/'position_evaluation_binding.json').write_text(json.dumps(seal,indent=2)+'\n')
    old={(r['case'],r['arm']):r for r in csv.DictReader(OLD.open())}
    rows=[]
    for case in results['rows']:
        for arm in ARMS:
            baseline=old[(case['case'],arm)]
            assert int(baseline['baseline_associated'])==case['baseline'][arm]['associated']
            base_error=float(baseline['baseline_error_m'])
            for method in METHODS:
                state=case['variants'].get(method)
                selected=state['selected_output'][arm] if state else dict(source='exact_saved_ALGO07',
                    objective=case['baseline'][arm]['objective'],associated=case['baseline'][arm]['associated'])
                error=base_error if selected['source']=='exact_saved_ALGO07' else error_m(selected['x'])
                assert np.isfinite(error) and selected['associated']==case['baseline'][arm]['associated']
                rows.append(dict(case=case['case'],dataset=case['dataset'],arm=arm,method=method,
                    baseline_error_m=base_error,error_m=error,change_m=error-base_error,
                    stage_accepted=bool(state and state['accepted']),
                    output_source=selected['source'],stage_status=state['status'] if state else 'saved_comparator',
                    execution_status=case['status'],associated_points=selected['associated'],
                    objective=selected['objective'],saved_objective=case['baseline'][arm]['objective'],
                    rms_hz=selected.get('rms_hz'),
                    target_family=case.get('target_family'),
                    prior_status=case.get('prior_receipt',{}).get('status'),
                    prior_reason=case.get('prior_receipt',{}).get('reason')))
    csv_write(ROOT/'position_results.csv',rows)
    aggregates=[]
    panel={'DS26-0070','DS26-0309','DS26-0040','DS26-0044','FRSH-0004'}
    for scope in ['ALL',*COHORTS,'EXCLUDE_FIVE_CHALLENGE']:
        for arm in ARMS:
            for method in METHODS:
                selected=[r for r in rows if r['arm']==arm and r['method']==method and
                    (scope=='ALL' or scope==r['dataset'] or scope=='EXCLUDE_FIVE_CHALLENGE' and r['case'] not in panel)]
                aggregates.append(dict(scope=scope,arm=arm,method=method,**metrics(selected)))
    csv_write(ROOT/'cohort_statistics.csv',aggregates)
    # Isolate the incremental covariance effect from the numerical repair.
    comparisons=[]
    keyed={(r['case'],r['arm'],r['method']):r for r in rows}
    for scope in ['ALL',*COHORTS]:
        for arm in ARMS:
            for before,after in [('ALGO07','A'),('A','A+B'),('A+B','A+B+C')]:
                selected=[r for r in rows if r['arm']==arm and r['method']==after
                          and (scope=='ALL' or r['dataset']==scope)]
                differences=np.asarray([r['error_m']-keyed[(r['case'],arm,before)]['error_m'] for r in selected])
                comparisons.append(dict(scope=scope,arm=arm,before=before,after=after,count=len(selected),
                    mean_change_m=float(differences.mean()),median_change_m=float(np.median(differences)),
                    improved_over50m=int(np.sum(differences < -50)),regressed_over50m=int(np.sum(differences > 50)),
                    maximum_regression_m=float(max(0,differences.max()))))
    csv_write(ROOT/'incremental_comparisons.csv',comparisons)
    findings=dict(binding=seal,scope='same-site retrospective development; no new-location validation',
        case_status_counts=dict(Counter(r['status'] for r in results['rows'])),
        stage_status_counts={m:dict(Counter(r['variants'][m]['status'] for r in results['rows'])) for m in METHODS[1:]},
        prior_status_counts=dict(Counter(r.get('prior_receipt',{}).get('reason','not_reached') for r in results['rows'])),
        cases=len(results['rows']),all_association_counts_unchanged=True,aggregates=aggregates)
    (ROOT/'position_summary.json').write_text(json.dumps(findings,indent=2)+'\n')

    fig,axes=plt.subplots(2,3,figsize=(14,8))
    for ax,scope in zip(axes.flat,['ALL',*COHORTS]):
        for method in METHODS:
            selected=sorted(r['error_m']/1000 for r in rows if r['arm']=='fitted_c' and r['method']==method and (scope=='ALL' or r['dataset']==scope))
            ax.step(selected,100*np.arange(1,len(selected)+1)/len(selected),where='post',label=method,color=COLORS[method],linestyle=STYLES[method])
        ax.axvline(.5,color='black',ls=':',alpha=.5)
        ax.set_title(scope+' — fitted c');ax.set_xlabel('Position error (km)');ax.set_ylabel('Scans at or below error (%)')
        ax.set_ylim(0,102);ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8)
    fig.suptitle('Same available scans, with every fallback retained; 0.5 km goal dotted')
    fig.tight_layout(rect=(0,0,1,.96));fig.savefig(ROOT/'position_error_cdfs.png',dpi=170);plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(13,4.8),sharey=True)
    for ax,arm in zip(axes,ARMS):
        for method in METHODS:
            selected=sorted(r['error_m']/1000 for r in rows if r['arm']==arm and r['method']==method)
            ax.step(selected,100*np.arange(1,len(selected)+1)/len(selected),where='post',label=method,color=COLORS[method],linestyle=STYLES[method])
        ax.axvline(.5,color='black',ls=':',alpha=.5);ax.set_title(arm);ax.set_xlabel('Position error (km)')
        ax.set_ylabel('Scans at or below error (%)');ax.grid(alpha=.2);ax.set_ylim(0,102)
    axes[0].legend();fig.suptitle('All 205 scans: controlled c ablation, including unchanged fallbacks')
    fig.tight_layout(rect=(0,0,1,.94));fig.savefig(ROOT/'paired_c_error_cdfs.png',dpi=170);plt.close(fig)

    fig,axes=plt.subplots(1,3,figsize=(15,5),sharex=True,sharey=True)
    for ax,method in zip(axes,METHODS[1:]):
        data=[r for r in rows if r['arm']=='fitted_c' and r['method']==method]
        for cohort in COHORTS:
            subset=[r for r in data if r['dataset']==cohort]
            ax.scatter([r['baseline_error_m']/1000 for r in subset],[r['error_m']/1000 for r in subset],s=22,label=cohort,alpha=.7)
        maximum=max(max(r['baseline_error_m'],r['error_m']) for r in data)/1000+.2
        ax.plot([0,maximum],[0,maximum],color='gray',ls='--',lw=1)
        for r in sorted([r for r in data if abs(r['change_m'])>50],key=lambda r:abs(r['change_m']),reverse=True)[:3]:
            ax.annotate(r['case'],(r['baseline_error_m']/1000,r['error_m']/1000),fontsize=7,
                        xytext=(-3,3),ha='right',textcoords='offset points')
        ax.set_title(method);ax.set_xlabel('ALGO07 error (km)');ax.set_ylabel('Candidate policy error (km)');ax.grid(alpha=.2)
    axes[0].legend(fontsize=8);fig.suptitle('Fitted-c per-scan comparison: below diagonal improves')
    fig.tight_layout(rect=(0,0,1,.94));fig.savefig(ROOT/'position_error_scatter.png',dpi=170);plt.close(fig)
    challenge=[r for r in rows if r['case'] in panel]
    csv_write(ROOT/'challenge_cases.csv',challenge)
    fig,axes=plt.subplots(1,2,figsize=(13,5),sharey=True)
    challenge_ids=sorted(panel)
    for ax,arm in zip(axes,ARMS):
        for index,method in enumerate(METHODS[:3]):
            values=[keyed[(case,arm,method)]['error_m']/1000 for case in challenge_ids]
            ax.bar(np.arange(len(challenge_ids))+(index-1)*.25,values,width=.25,label=method,color=COLORS[method])
        ax.set_xticks(np.arange(len(challenge_ids)),challenge_ids,rotation=30,ha='right')
        ax.set_title(arm);ax.set_ylabel('Position error (km)');ax.grid(axis='y',alpha=.2)
        ax.axhline(.5,color='black',ls=':',alpha=.5)
    axes[0].legend();fig.suptitle('Five previously investigated cases — development diagnostics')
    fig.tight_layout(rect=(0,0,1,.94));fig.savefig(ROOT/'challenge_case_errors.png',dpi=170);plt.close(fig)
    lines=['# Position outcomes after sealed RF decisions','',
           'All results are same-site retrospective development evidence. Every unchanged fallback remains in the denominator.',
           'A is the numerical repair; A+B adds the causal-history covariance; A+B+C gates that same endpoint with other-family support.','',
           '| Cohort | n | Arm | Policy | Mean km | Median km | p90 km | Below 500 m | Improve / regress >50 m |',
           '| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for r in aggregates:
        lines.append(f"| {r['scope']} | {r['count']} | {r['arm']} | {r['method']} | {r['mean_m']/1000:.3f} | {r['median_m']/1000:.3f} | {r['p90_m']/1000:.3f} | {r['below_500m_percent']:.1f}% | {r['improved_over50m']} / {r['regressed_over50m']} |")
    lines.extend(['','![Fitted-c cohort distributions](position_error_cdfs.png)','',
                  '![Matched calibration arms](paired_c_error_cdfs.png)','',
                  '![Per-scan comparison](position_error_scatter.png)','',
                  '![Previously investigated cases](challenge_case_errors.png)','',
                  '[Exact statistics](cohort_statistics.csv) · [Incremental policy comparisons](incremental_comparisons.csv) · [All scan/arm/policy rows](position_results.csv) · [Evaluation binding](position_evaluation_binding.json)','',
                  'These are conditional graph/model refinements of saved ALGO07 outputs, not raw-IQ pipeline reruns or new-site validation. Association counts are unchanged.'])
    (ROOT/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps([r for r in aggregates if r['scope']=='ALL'],indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--audit',type=Path,required=True)
    args=parser.parse_args()
    main(args.results,args.audit)
