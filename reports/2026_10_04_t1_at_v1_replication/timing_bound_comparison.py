"""Matched 18-scan localization ablation: absolute satellite timing +/-20 vs +/-10 s.

Frozen associated windows, bank and cross-fitted receiver baseline. No new
association search or upstream recalibration. Same priors and 4 km search disk.
Bounded multistart local searches, not global minimum certificates.
"""
import argparse
import csv
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
from leave_one_satellite_out import load
from subset_positions import enable_research_model, serial
from convergence_fisher import fit
from resume_position_convergence import best_record

HERE = Path(__file__).resolve().parent
OUT = HERE/'timing-bound-10s-vs-20s'
SCANS = ['A','B']+[f'N{i:02}' for i in range(1,17)]
ARMS = ['fitted-c','zero-c']
RADIUS = 4.
BUDGET = dict(roof=4., probe=1., search=8., polish=8.)


def digest(path):
    return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def feasible_start(obj, record, limit, arm):
    """Clip total shifts individually, then exactly reconstruct common/relative."""
    p=np.asarray(record['parameters']).copy()
    total=np.clip(p[6:],-limit+2e-6,limit-2e-6)
    common=float(np.mean(total))
    common=float(np.clip(common,-10.+1e-8,10.-1e-8))
    # All total shifts in this experiment have mean inside the common bound.
    return np.r_[p[:6],common,obj.base.basis.T@(total-common),
                 record['coefficient'] if arm=='fitted-c' else 0.]


def extra_start(scan, arm, fallback):
    branch=HERE/'N12-62866-62868-identity-audit/full-bank-timing-branch-check.json'
    baseline=HERE/'leave-one-out-N12-N15-4km'/scan/'baseline.json'
    if scan=='N12' and branch.exists():
        return json.loads(branch.read_text())['arms'][arm]['best'],branch
    if baseline.exists():
        return json.loads(baseline.read_text())['arms'][arm]['best'],baseline
    return fallback,None


def run(scan):
    enable_research_model()
    from rf_calibration_diagnostic import CalibrationObjective
    data,meta,old=load(scan)
    for arm in ARMS:
        old_best=old['arms'][arm]['best']; old_roof=old['arms'][arm]['roof']
        extra,extra_path=extra_start(scan,arm,old_best)
        for limit in (20.,10.):
            target=OUT/f'{scan}-{arm}-{int(limit)}s.json'
            if target.exists():
                assert json.loads(target.read_text())['input_sha256']==meta['input_sha256']
                continue
            obj=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,60.)
            obj.center=meta['rf_center_hz']
            obj.features=((data.rf-obj.center)/1e9)[:,None]
            obj.likelihood.features=obj.features
            obj.base.minimum_shift_s=max(obj.base.minimum_shift_s,-limit)
            obj.base.maximum_shift_s=min(obj.base.maximum_shift_s,limit)
            if arm=='zero-c':obj.bounds[-1]=(0.,0.)
            records=[]
            def fitted(stage,record,point,budget,fixed=False):
                start=feasible_start(obj,record,limit,arm)
                r=fit(obj,start,point,budget,fixed,radius_km=RADIUS)
                r['stage']=stage;records.append(r)
                assert np.max(np.abs(np.asarray(r['parameters'])[6:]))<=limit+1e-7
                assert np.linalg.norm(r['point_km'])<=RADIUS+1e-7
                return r
            roof=fitted('roof',old_roof,[0.,0.],BUDGET['roof'],True)
            probes=[]
            for i,angle in enumerate(np.arange(4)*np.pi/2):
                point=3.2*np.array([np.cos(angle),np.sin(angle)])
                probes.append(fitted(f'probe-{i}',roof,point,BUDGET['probe'],True))
            ring=min(probes,key=lambda r:r['objective'])
            starts=[roof,old_best,extra if extra_path else ring]
            for i,seed in enumerate(starts):
                fitted(f'search-{i}',seed,seed['point_km'],BUDGET['search'])
            best=best_record(records)
            fitted('polish',best,best['point_km'],BUDGET['polish'])
            best=best_record(records)
            obj.base.deadline=float('inf')
            score,_=obj.evaluate(np.asarray(best['vector']))
            assert abs(score-best['objective'])<1e-7
            penalty,_=obj.base.penalty(np.asarray(best['vector'])[:obj.size])
            probability=obj.likelihood.last_result['row_association_probability']
            total=np.asarray(best['parameters'])[6:]
            result=dict(scan=scan,arm=arm,total_timing_bound_s=limit,radius_km=RADIUS,
                scope=__doc__,input_sha256=meta['input_sha256'],windows=len(data.times),
                numbers=data.numbers,priors_unchanged=True,maximum_budgets_s=BUDGET,
                implementation_sha256={str(p):digest(p) for p in (Path(__file__),HERE/'convergence_fisher.py')},
                extra_start_source=str(extra_path) if extra_path else None,
                extra_start_sha256=digest(extra_path) if extra_path else None,
                previous_2km_distance_m=1000*np.linalg.norm(old_best['point_km']),
                best=best,records=records,distance_m=1000*np.linalg.norm(best['point_km']),
                converged=bool(best['success'] and not best['fixed_location']),
                boundary=bool(np.linalg.norm(best['point_km'])>=RADIUS-1e-4),
                timing_boundary_count=int(sum(abs(total)>=limit-1e-3)),
                maximum_absolute_timing_s=float(max(abs(total))),timing_prior_nll=penalty,
                data_nll=score-penalty,objective=score,
                strong_soft_windows=int(sum(np.max(probability,axis=1)>.5)),
                elapsed_s=sum(r['elapsed_s'] for r in records))
            target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
            print('DONE',scan,arm,limit,round(result['distance_m']),best['status'],
                  'timing-bound',result['timing_boundary_count'],flush=True)
    return scan


def render():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    rows=[]
    for scan in SCANS:
        for arm in ARMS:
            for limit in (20,10):
                p=OUT/f'{scan}-{arm}-{limit}s.json'
                if p.exists():rows.append(json.loads(p.read_text()))
    keys=['scan','arm','total_timing_bound_s','windows','distance_m','previous_2km_distance_m',
          'converged','boundary','objective','data_nll','timing_prior_nll',
          'timing_boundary_count','maximum_absolute_timing_s','strong_soft_windows','elapsed_s','input_sha256']
    with (OUT/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(rows)
    lookup={(r['scan'],r['arm'],int(r['total_timing_bound_s'])):r for r in rows}
    assert len(lookup)==72,'Wait for every matched comparison before plotting'
    fig,axes=plt.subplots(2,1,figsize=(15,9),sharex=True,sharey=True)
    for ax,arm in zip(axes,ARMS):
        for i,scan in enumerate(SCANS):
            a,b=[lookup[scan,arm,k] for k in (20,10)]
            assert a['input_sha256']==b['input_sha256'] and a['numbers']==b['numbers']
            ax.plot([i-.13,i+.13],[a['distance_m'],b['distance_m']],color='.65',lw=1.5,zorder=1)
            for dx,r,color in [(-.13,a,'#888888'),(.13,b,'#0077ad')]:
                ax.scatter(i+dx,r['distance_m'],marker='^' if r['boundary'] else 'o',s=60,
                           facecolor=color if r['converged'] else 'white',edgecolor=color,zorder=3)
                if not r['converged']:ax.scatter(i+dx,r['distance_m'],marker='x',s=30,color='black',zorder=4)
            ax.annotate(f"{b['distance_m']:.0f}",(i+.13,b['distance_m']),xytext=(0,9),textcoords='offset points',ha='center',fontsize=8,color='#0077ad')
        old=np.array([lookup[s,arm,20]['distance_m'] for s in SCANS])
        new=np.array([lookup[s,arm,10]['distance_m'] for s in SCANS])
        ax.set_title(('Fitted c' if arm=='fitted-c' else 'c = 0')+
                     f' · median position error {np.median(old):.0f} → {np.median(new):.0f} m')
        ax.axhline(4000,color='.5',ls=':',lw=1);ax.set_ylim(-100,4430)
        ax.set_ylabel('Distance from known roof (m)');ax.grid(axis='y',alpha=.18)
    axes[-1].set_xticks(range(len(SCANS)),SCANS)
    fig.suptitle('T1-AT v1 · tightening absolute satellite timing: ±20 s → ±10 s',fontsize=18,y=.98)
    handles=[Line2D([],[],marker='o',ls='none',color=c,label=l) for c,l in [('#888888','±20 s control (rerun)'),('#0077ad','±10 s')]]
    handles += [Line2D([],[],marker='^',ls='none',color='.3',label='4 km position boundary'),Line2D([],[],marker='x',ls='none',color='black',label='Unconverged')]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.065),ncol=4,frameon=False)
    fig.text(.5,.02,'Independent scans; all originally associated windows retained. Same frozen RX baseline, bank, priors and maximum search budgets.\n'
             'Bound applies to total shift τ + δs. No association rerun; no upstream recalibration. Local best-found results, not global minima.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.115,1,.95));fig.savefig(OUT/'position-error-comparison.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(14,5.2))
    for arm,color in zip(ARMS,['#0077ad','#df6900']):
        deltas=[];scores=[]
        for s in SCANS:
            a,b=lookup[s,arm,20],lookup[s,arm,10]
            deltas.append(b['distance_m']-a['distance_m']);scores.append(b['objective']-a['objective'])
        axes[0].plot(SCANS,deltas,'o-',label=arm,color=color)
        axes[1].plot(SCANS,scores,'o-',label=arm,color=color)
    for ax in axes:ax.axhline(0,color='.4',lw=1);ax.grid(alpha=.15);ax.tick_params(axis='x',rotation=45);ax.legend()
    axes[0].set_ylabel('Position error change (m) · negative is better')
    axes[1].set_ylabel('NLL change · negative is a better local score')
    fig.suptitle('Timing bound effect: position accuracy and fit score are different outcomes')
    fig.text(.5,.015,'Δ = ±10 s minus ±20 s. A lower score under tighter bounds indicates a missed local mode in the ±20 s search.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.06,1,.95));fig.savefig(OUT/'score-vs-position-change.png',dpi=170);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--render-only',action='store_true');p.add_argument('--workers',type=int,default=3)
    args=p.parse_args();OUT.mkdir(exist_ok=True)
    if not args.render_only:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(run,s) for s in SCANS]):print('SCAN COMPLETE',future.result(),flush=True)
    render()
