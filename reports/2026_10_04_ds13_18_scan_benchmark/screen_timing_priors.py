"""Development-only actual Gaussian timing-prior width experiment.

Frozen baseline alternative-candidate memberships and nonlinear RX correction.
Each RF/prior arm has identical three position starts and fit budgets. This is
a bounded conditional position screen, not a full reassociation or global search.
Report likelihood and prior penalty separately; scores across prior widths do
not define a common model ranking. No locked-test inference is permitted here.
"""
import argparse
import inspect
import json
from pathlib import Path

import numpy as np
from cohort import digest
from fisher_position import fit
from position_search import prepare
from timing_prior_scale import apply

HERE=Path(__file__).resolve().parent
SCALES=(.5,1.,2.)
STARTS=((0.,0.),(1.,0.),(0.,-1.))


def check_split(cohort,label):
    if next((r['split'] for r in cohort['scans'] if r['label']==label),None)!='development':
        raise ValueError('timing-prior screening accepts development scans only')


def decompose(objective,record):
    vector=np.asarray(record['vector'])
    value,_=objective.evaluate(vector)
    penalty,_=objective.base.penalty(vector[:objective.size])
    if abs(value-record['objective'])>1e-6:
        raise ValueError('saved timing-prior objective does not reconstruct')
    return dict(data_nll=float(value-penalty),timing_penalty=float(penalty))


def run(inputs,label):
    cohort_path=HERE/'cohort-v2.json'
    check_split(json.loads(cohort_path.read_text()),label)
    directory=inputs/label/'seed-timing-v6'
    data,meta=prepare(directory,'alternatives','support',1.)
    from rf_calibration_diagnostic import CalibrationObjective
    from timing_model import TimingObjective
    mean=float(np.mean(data.initial[6:]))
    data.initial[6:]*=min(1.,(10-1e-6)/max(abs(mean),10-1e-6))
    data.initial[6:]=np.clip(data.initial[6:],-20+1e-6,20-1e-6)
    root=directory/'timing-prior-screen-v1'
    root.mkdir(exist_ok=True)
    implementations=[Path(__file__),Path(inspect.getfile(fit)),Path(inspect.getfile(apply)),
                     Path(inspect.getfile(prepare)),Path(inspect.getfile(CalibrationObjective)),
                     Path(inspect.getfile(TimingObjective))]
    sources={str(p):digest(p.read_bytes()) for p in implementations+[cohort_path]}
    rows=[]
    for width in SCALES:
        signature=dict(inputs=meta,sources=sources,prior_width_scale=width,
                       starts=STARTS,budget_per_fit_s=20.,scope=__doc__)
        # JSON round-trip canonicalizes tuple-valued starts for cache matching.
        signature=json.loads(json.dumps(signature))
        for arm in ('fitted-c','zero-c'):
            objective=apply(CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,20.),width)
            objective.base.minimum_shift_s=max(objective.base.minimum_shift_s,-20.)
            objective.base.maximum_shift_s=min(objective.base.maximum_shift_s,20.)
            if arm=='zero-c':objective.bounds[-1]=(0.,0.)
            initial=objective.initial.copy();initial[-1]=meta['seed_coefficient'] if arm=='fitted-c' else 0.
            records=[]
            def saved(name,start,point,fixed):
                path=root/f'{arm}-width{width:g}-{name}.json'
                if path.exists():
                    document=json.loads(path.read_text())
                    if document['signature']!=signature:raise ValueError('prior screen cache mismatch')
                    result=document['result']
                else:
                    result=fit(objective,start,point,20.,fixed)
                    result.update(decompose(objective,result));result['stage']=name
                    with path.open('x') as stream:
                        json.dump(dict(signature=signature,result=result),stream,allow_nan=False)
                records.append(result)
                print('PRIOR',label,width,arm,name,round(result['objective'],3),result['success'],flush=True)
                return result
            roof=saved('roof',initial,[0.,0.],True)
            for index,point in enumerate(STARTS):
                saved(f'joint-{index}',roof['vector'],point,False)
            best=min(records,key=lambda r:r['objective'])
            rechecked=saved('roof-transfer',best['vector'],[0.,0.],True)
            roof=min((roof,rechecked),key=lambda r:r['objective'])
            best=min(records,key=lambda r:r['objective'])
            rows.append(dict(scan=label,arm=arm,prior_width_scale=width,
                             common_sigma_s=10*width,individual_sigma_s=width,
                             radius_m=float(1000*np.linalg.norm(best['point_km'])),
                             boundary=bool(np.linalg.norm(best['point_km'])>1.999),
                             best_joint_stationary=bool(best['success'] and not best['fixed_location']),
                             roof_converged=roof['success'],best=best,roof=roof,records=records))
    output=HERE/'timing-prior-screen'
    output.mkdir(exist_ok=True)
    checkpoints={str(p):digest(p.read_bytes()) for p in root.glob('*.json')}
    (output/f'{label}.json').write_text(json.dumps(dict(scope=__doc__,inputs=meta,sources=checkpoints,rows=rows),indent=2,allow_nan=False))
    render(output,label)


def render(output,label):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    document=json.loads((output/f'{label}.json').read_text())
    for path,expected in document['sources'].items():
        if digest(Path(path).read_bytes())!=expected:raise ValueError('stale prior-screen checkpoint')
    fig,axes=plt.subplots(1,3,figsize=(14,5))
    for arm,color in (('fitted-c','#0072b2'),('zero-c','#d55e00')):
        rows=sorted((r for r in document['rows'] if r['arm']==arm),key=lambda r:r['prior_width_scale'])
        xx=[r['prior_width_scale'] for r in rows]
        for ax,field in zip(axes,('radius_m','data_nll','timing_penalty')):
            yy=[r[field] if field=='radius_m' else r['best'][field] for r in rows]
            ax.plot(xx,yy,'o-',color=color,label=arm)
            for x,y,r in zip(xx,yy,rows):
                if not r['best_joint_stationary']:ax.plot(x,y,'kx',ms=11)
                if r['boundary']:ax.plot(x,y,'^',mfc='none',mec='black',ms=12)
            ax.set(xticks=SCALES,xlabel='Timing prior standard-deviation multiplier')
            ax.grid(alpha=.15);ax.legend()
    for ax,title in zip(axes,('Best-found distance from roof (m)','Data NLL at best saved fit','Timing-prior penalty at best saved fit')):
        ax.set_title(title)
    fig.suptitle(f'{label} · actual Gaussian timing-prior sensitivity',fontsize=15)
    fig.text(.5,.015,'Same frozen observations and candidate bank; three matched position starts, 20 s per fit. Not a global certificate.\nCross = not jointly stationary; triangle = 2 km boundary. Different-width penalized totals are not directly comparable.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.12,1,.92));fig.savefig(output/f'{label}.png',dpi=150);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',type=Path);p.add_argument('--label',required=True)
    a=p.parse_args();run(a.inputs,a.label)
