"""Evaluate sealed later baseline endpoints only after complete RF nomination."""
import csv
import hashlib
import json
import math
from pathlib import Path
import time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
BASE = Path('/srv/bulk/leo/research/ds24-later-four-preparation-r01/baseline')
WORK = BASE/'work'
NOM = BASE/'nomination'
CASES = tuple(f'LATER4-{i:04}' for i in range(1,5))


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def latlon(x):
    return 37.906+x[1]/111., -122.545+x[0]/(111.32*math.cos(math.radians(37.906)))


def distance(a,b):
    a0,a1,b0,b1=map(math.radians,(*a,*b))
    h=math.sin((b0-a0)/2)**2+math.cos(a0)*math.cos(b0)*math.sin((b1-a1)/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1.,max(0.,h))))


def verify_seal(path):
    for p,h in read(path)['files'].items():
        if sha(p)!=h:
            raise ValueError('sealed RF file changed: '+p)


def main():
    started=time.monotonic()
    go=read(ROOT/'later_geography_go.json')
    if not go['authorized'] or go['evaluator_sha256']!=sha(__file__):
        raise ValueError('exact evaluator release required')
    for name,seal in [('baseline',BASE/'later_RF_seal.json'),('nomination',NOM/'RF_seal.json')]:
        if sha(seal)!=go[name+'_RF_seal_sha256']:
            raise ValueError('RF seal differs from released result')
        verify_seal(seal)
        audit=read(ROOT/'audit'/(name+'_terminal.json'))
        if not audit['all_passed']:
            raise ValueError('passing terminal audit required')
        if audit[name+'_RF_seal_sha256']!=sha(seal):
            raise ValueError('terminal audit belongs to a different RF seal')
    reference=go['reference_latlon']
    members={m['dataset_label']:m for m in read(WORK/'sample.json')['selected']}
    execution={r['case']:r for r in read(BASE/'later_execution.json')['rows']}
    nominations={r['case']:r for r in read(NOM/'summary.json')['rows']}
    rows=[]
    for case in CASES:
        complete=execution[case]['status']=='complete'
        result=read(WORK/'family_cavity/position'/(case+'.json')) if complete else None
        own=read(NOM/case/'ownership.json') if (NOM/case/'ownership.json').exists() else None
        for arm in ['c0','fitted_c']:
            row=dict(case=case,recording_id=members[case]['recording_id'],arm=arm,
                     baseline_status=execution[case]['status'],nomination_status=nominations[case]['status'],
                     position_error_km=None,associated_points=None,associated_percent=None,
                     likelihood_points=None,likelihood_percent=None,GLRT_points=None,
                     target_points=nominations[case].get('target_IDs'),control_points=nominations[case].get('control_IDs'))
            if complete:
                saved=result['policy_arms'][arm]
                x=saved['endpoint_east_north_km']
                if len(x)!=2 or not all(math.isfinite(v) and abs(v)<=12.5 for v in x):
                    raise ValueError('invalid regional endpoint')
                row.update(east_km=x[0],north_km=x[1],position_error_km=distance(latlon(x),reference))
                phases=saved['state']['phases']
                phase_max=max((abs(float(v)) for v in phases),default=0.)
                row.update(maximum_absolute_phase_s=phase_max,
                           within_15s_phase_diagnostic=phase_max<=15.000001)
            if own:
                cov=own['coverage'][arm]
                row.update(associated_points=cov['associated'],associated_percent=cov['percent'],
                           likelihood_points=cov['likelihood_points'],likelihood_percent=cov['likelihood_percent'],
                           GLRT_points=cov['total_GLRT'])
            rows.append(row)
    out=ROOT/'later_geographic'
    out.mkdir(exist_ok=False)
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with (out/'per_scan.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(rows)
    stats={}
    for arm in ['c0','fitted_c']:
        errors=[r['position_error_km'] for r in rows if r['arm']==arm and r['position_error_km'] is not None]
        stats[arm]=dict(successes=len(errors),attempted=4,mean_km=float(np.mean(errors)) if errors else None,
                        median_km=float(np.median(errors)) if errors else None,max_km=max(errors) if errors else None)
    fig,axes=plt.subplots(1,2,figsize=(12.6,4.5),layout='constrained')
    x=np.arange(4)
    for arm,dx,color,label in [('c0',-.18,'#176b8b','c = 0'),('fitted_c',.18,'#b06624','Fitted c')]:
        group=[next(r for r in rows if r['case']==case and r['arm']==arm) for case in CASES]
        for index,row in enumerate(group):
            error=row['position_error_km']
            if error is not None:
                axes[0].bar(index+dx,error,.34,color=color,label=label if index==0 else None)
                axes[0].text(index+dx,error+.025,f'{error:.2f}',ha='center',va='bottom',fontsize=9)
            else:
                axes[0].text(index+dx,0,'Unavailable',rotation=90,ha='center')
    for dx,key,color,label in [(-.18,'likelihood_percent','#176b8b','Position likelihood'),(.18,'associated_percent','#714d86','All compatible associations')]:
        vals=[next(r for r in rows if r['case']==case and r['arm']=='fitted_c')[key] for case in CASES]
        for i,v in enumerate(vals):
            if v is not None:
                axes[1].bar(i+dx,v,.34,color=color,label=label if i==0 else None)
                axes[1].text(i+dx,v+.8,f'{v:.1f}',ha='center',va='bottom',fontsize=8)
    for ax in axes:
        labels=[]
        for i,case in enumerate(CASES,1):
            flagged=any(r.get('within_15s_phase_diagnostic') is False for r in rows if r['case']==case)
            labels.append(f'L4-{i}'+('*' if flagged else ''))
        ax.set_xticks(x,labels);ax.grid(axis='y',alpha=.25);ax.legend(fontsize=9)
    axes[0].set_title('Retained baseline position error');axes[0].set_ylabel('Error (km)')
    axes[1].set_title('Fitted-c coverage: different evidence roles');axes[1].set_ylabel('% of original GLRT winners');axes[1].set_ylim(0,105)
    fig.suptitle('Four fixed later fast recordings · no CFO correction applied\n* Absolute phase exceeds 15 s; the original producer accepts this endpoint',fontsize=12)
    for extension in ['png','pdf']:
        fig.savefig(out/f'baseline_position_and_coverage.{extension}',dpi=170)
    plt.close(fig)
    summary=dict(rows=rows,statistics=stats,new_fits=0,no_CFO_correction=True,
                 evaluation_authority_sha256=sha(ROOT/'EVALUATION_AUTHORITY.md'),reference_latlon=reference,
                 not_an_untouched_holdout=True,reporting_seconds=time.monotonic()-started)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    paths=[Path(__file__),ROOT/'later_geography_go.json',BASE/'later_RF_seal.json',NOM/'RF_seal.json',*out.iterdir()]
    (out/'seal.json').write_text(json.dumps({'files':{str(p):sha(p) for p in paths}},indent=2)+'\n')
    print(json.dumps(stats))


if __name__=='__main__':
    main()
