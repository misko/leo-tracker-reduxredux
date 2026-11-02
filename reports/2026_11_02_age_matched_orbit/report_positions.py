"""Postdecision geographic comparison; never imported by RF workers."""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent
PREVIOUS=ROOT.parent/'2026_11_02_generalized_corrections'
METHODS=['ALGO07','A','B','Age3','Age2']
COHORTS=['DS24','DS26','DS27','DS28','FRSH']
COLORS=dict(zip(METHODS,['#666666','#277da8','#e58b30','#3a9a68','#a04ab8']))
STYLES=dict(zip(METHODS,['-',':','--','-.','-']))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_csv(path,rows):
    with path.open('w') as stream:
        w=csv.DictWriter(stream,rows[0].keys());w.writeheader();w.writerows(rows)


def summarize(rows):
    errors=np.array([r['error_m'] for r in rows]);delta=np.array([r['change_vs_ALGO07_m'] for r in rows])
    return dict(n=len(rows),mean_m=float(errors.mean()),median_m=float(np.median(errors)),
        p90_m=float(np.percentile(errors,90)),p95_m=float(np.percentile(errors,95)),max_m=float(errors.max()),
        below500=int(np.sum(errors<500)),improved_over50m=int(np.sum(delta< -50)),regressed_over50m=int(np.sum(delta>50)),
        max_regression_m=float(max(0,delta.max())),associated_points=sum(r['associated_points'] for r in rows))


def main(result_path,audit_path):
    result=json.loads(result_path.read_text());audit=json.loads(audit_path.read_text())
    assert result['workers_joined'] and result['available']==205
    assert all(r['status'] not in ['running','pending'] for r in result['rows'])
    assert audit['status']=='passed' and audit['results_sha256']==sha(result_path)
    binding=dict(created_utc_ns=time.time_ns(),results_sha256=sha(result_path),audit_sha256=sha(audit_path),
        protocol_sha256=sha(ROOT/'protocol.json'),previous_positions_sha256=sha(PREVIOUS/'position_results.csv'),
        purpose='Geographic evaluation only after fixed RF decisions and independent audit',workers_joined=True)
    (ROOT/'position_binding.json').write_text(json.dumps(binding,indent=2)+'\n')
    spec=importlib.util.spec_from_file_location('previous_geo_reporting',PREVIOUS/'evaluate_positions.py')
    old_report=importlib.util.module_from_spec(spec);spec.loader.exec_module(old_report)
    old={(r['case'],r['arm'],r['method']):r for r in csv.DictReader((PREVIOUS/'position_results.csv').open())}
    rows=[]
    for case in result['rows']:
        for arm in ['c0','fitted_c']:
            base=old[case['case'],arm,'ALGO07'];a=old[case['case'],arm,'A'];b=old[case['case'],arm,'A+B']
            for method in METHODS:
                if method in ['ALGO07','A','B']:
                    original={'ALGO07':base,'A':a,'B':b}[method]
                    error=float(original['error_m']);count=int(original['associated_points']);accepted=original['stage_accepted']=='True'
                    source=original['output_source']
                else:
                    policy=case['policies'][method];output=policy['selected_output'][arm]
                    error=old_report.error_m(output['x']) if policy['accepted'] else float(a['error_m'])
                    count=output['associated'];accepted=policy['accepted'];source=output['source']
                assert count==int(base['associated_points']) and np.isfinite(error)
                rows.append(dict(case=case['case'],dataset=case['dataset'],arm=arm,method=method,error_m=error,
                    change_vs_ALGO07_m=error-float(base['error_m']),change_vs_A_m=error-float(a['error_m']),
                    change_vs_B_m=error-float(b['error_m']),associated_points=count,accepted=accepted,source=source,
                    execution_status=case['status'],target_family=case.get('target_family'),
                    pair_count=case.get('age_prior_receipt',{}).get('pair_count'),
                    prior_reason=case.get('age_prior_receipt',{}).get('reason')))
    write_csv(ROOT/'positions.csv',rows)
    stats=[]
    for scope in ['ALL',*COHORTS]:
        for arm in ['c0','fitted_c']:
            for method in METHODS:
                subset=[r for r in rows if r['method']==method and r['arm']==arm and (scope=='ALL' or r['dataset']==scope)]
                stats.append(dict(scope=scope,arm=arm,method=method,**summarize(subset)))
    write_csv(ROOT/'statistics.csv',stats)
    summary=dict(binding=binding,scope='same-site retrospective development, unchanged association coverage',
        policy_accepted=result['policy_accepted'],status_counts=result['status_counts'],statistics=stats)
    (ROOT/'position_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    fig,axes=plt.subplots(2,3,figsize=(14,8))
    for ax,scope in zip(axes.flat,['ALL',*COHORTS]):
        for method in METHODS:
            errors=sorted(r['error_m']/1000 for r in rows if r['method']==method and r['arm']=='fitted_c' and (scope=='ALL' or r['dataset']==scope))
            ax.step(errors,100*np.arange(1,len(errors)+1)/len(errors),where='post',label=method,color=COLORS[method],ls=STYLES[method],lw=1.6)
        ax.axvline(.5,color='black',ls=':',alpha=.5);ax.set_title(scope+' — fitted c')
        ax.set_xlabel('Position error (km)');ax.set_ylabel('Scans at or below error (%)');ax.grid(alpha=.2);ax.set_ylim(0,102)
    axes[0,0].legend(fontsize=8)
    fig.suptitle('Age-matched covariance: all available recordings and unchanged fallbacks')
    fig.tight_layout(rect=(0,0,1,.96));fig.savefig(ROOT/'cohort_error_cdfs.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5),sharey=True)
    for ax,arm in zip(axes,['c0','fitted_c']):
        for method in METHODS:
            errors=sorted(r['error_m']/1000 for r in rows if r['method']==method and r['arm']==arm)
            ax.step(errors,100*np.arange(1,len(errors)+1)/len(errors),where='post',label=method,color=COLORS[method],ls=STYLES[method])
        ax.axvline(.5,color='black',ls=':',alpha=.5);ax.set_title(arm);ax.set_xlabel('Position error (km)')
        ax.set_ylabel('Scans at or below error (%)');ax.grid(alpha=.2);ax.set_ylim(0,102)
    axes[0].legend();fig.suptitle('205 paired recordings — controlled c ablation')
    fig.tight_layout(rect=(0,0,1,.94));fig.savefig(ROOT/'paired_c_error_cdfs.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    keys={(r['case'],r['arm'],r['method']):r for r in rows}
    for ax,control in zip(axes,['A','B']):
        subset=[r for r in rows if r['method']=='Age2' and r['arm']=='fitted_c']
        x=np.array([keys[r['case'],'fitted_c',control]['error_m']/1000 for r in subset]);y=np.array([r['error_m']/1000 for r in subset])
        for cohort in COHORTS:
            use=np.array([r['dataset']==cohort for r in subset]);ax.scatter(x[use],y[use],s=23,label=cohort,alpha=.7)
        end=max(max(x),max(y))+.2;ax.plot([0,end],[0,end],color='gray',ls='--',lw=1)
        ax.set_xlabel(control+' error (km)');ax.set_ylabel('Age2 error (km)');ax.grid(alpha=.2)
        ax.set_title('Exploratory Age2 vs '+control)
    axes[0].legend(fontsize=8);fig.tight_layout();fig.savefig(ROOT/'paired_error_scatter.png',dpi=170);plt.close(fig)
    lines=['# Complete position statistics','',
        'ALGO07, A and B are immutable previous results. Age3 is the primary three-pair policy; Age2 is the exploratory two-pair policy. All unchanged fallbacks remain in each denominator.','',
        '| Cohort | Arm | Policy | n | Mean km | Median km | p90 km | p95 km | Below 500 m | Improve/regress >50 m |',
        '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in stats:
        lines.append(f"| {r['scope']} | {r['arm']} | {r['method']} | {r['n']} | {r['mean_m']/1000:.3f} | {r['median_m']/1000:.3f} | {r['p90_m']/1000:.3f} | {r['p95_m']/1000:.3f} | {r['below500']} | {r['improved_over50m']}/{r['regressed_over50m']} |")
    lines+=['','![Cohort distributions](cohort_error_cdfs.png)','','![Matched calibration arms](paired_c_error_cdfs.png)',
            '','![Per-scan comparison](paired_error_scatter.png)','','[All rows](positions.csv) · [Exact statistics](statistics.csv) · [Postdecision binding](position_binding.json)']
    (ROOT/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps([r for r in stats if r['scope']=='ALL'],indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--results',type=Path,required=True);parser.add_argument('--audit',type=Path,required=True)
    args=parser.parse_args();main(args.results,args.audit)
