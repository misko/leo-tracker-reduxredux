"""Matched original/post-scan orbit refits for every N01--N16 association set.

Same finite-set likelihood, all associated top-one windows, frozen upstream RX
baseline, satellite IDs, timing priors and bounds, and 4 km independent searches.
Orbit-only timing-aligned starts prevent a changed ephemeris from starting in a
different frequency-alias basin. No data-dependent TLE selection or position prior.
Retrospective diagnostic: future elements cannot be used in real-time inference.
"""
import argparse
import csv
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar
from post_scan_tle_bank import OUT,SCANS,load_variant
from leave_one_satellite_out import load
from subset_positions import enable_research_model,serial
from timing_bound_comparison import feasible_start,digest
from convergence_fisher import fit
from resume_position_convergence import best_record

enable_research_model()
from rf_calibration_diagnostic import CalibrationObjective
from prediction_jacobian import paired_prediction_jacobian

SOURCE=OUT.parent/'timing-bound-10s-vs-20s/cross-start-polish'
ARMS=('fitted-c','zero-c')
VARIANTS=('original','post-scan')
BUDGET=dict(roof=6.,probe=.5,search=6.,polish=6.)


def aligned_start(old,new,record):
    parameters=np.asarray(record['parameters']).copy();details=[]
    for j,number in enumerate(old.numbers):
        rows=np.flatnonzero(old.owners==number);ids=np.full(len(rows),j)
        if not len(rows):raise ValueError('No frozen owner rows for selected satellite')
        target=paired_prediction_jacobian(old,parameters,rows,ids)[0]
        trial=parameters.copy()
        def cost(total):
            trial[6+j]=total
            predicted=paired_prediction_jacobian(new,trial,rows,ids)[0]
            return float(np.mean((predicted-target)**2))
        grid=np.linspace(-20.+2e-6,20.-2e-6,41)
        values=np.array([cost(t) for t in grid]);k=int(np.argmin(values))
        refined=minimize_scalar(cost,bounds=(grid[max(0,k-1)],grid[min(40,k+1)]),method='bounded',options={'xatol':1e-7})
        old_total=float(parameters[6+j]);choices=[(float(values[k]),grid[k]),(refined.fun,refined.x),(cost(old_total),old_total)]
        value,total=min(choices)
        parameters[6+j]=total
        details.append(dict(satellite=int(number),old_total_s=old_total,aligned_total_s=float(total),
                            delta_s=float(total-old_total),alignment_rms_hz=float(np.sqrt(value))))
    return dict(record,parameters=parameters),details


def make_objective(data,meta,arm):
    obj=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,60.)
    obj.center=meta['rf_center_hz'];obj.features=((data.rf-obj.center)/1e9)[:,None];obj.likelihood.features=obj.features
    obj.base.minimum_shift_s=max(obj.base.minimum_shift_s,-20.)
    obj.base.maximum_shift_s=min(obj.base.maximum_shift_s,20.)
    if arm=='zero-c':obj.bounds[-1]=(0.,0.)
    obj.base.deadline=float('inf')
    return obj


def run(task):
    scan,arm,variant=task;target=OUT/scan/f'{arm}-{variant}.json'
    if target.exists():return str(target)
    data,meta,older,bank=load_variant(scan,variant);old=load(scan)[0]
    source=SOURCE/f'{scan}-{arm}-20s.json';previous=json.loads(source.read_text())
    assert previous['input_sha256']==meta['input_sha256']
    seeds=[older['arms'][arm]['roof'],previous['best']];alignments=[]
    if variant=='post-scan':
        aligned=[]
        for seed in seeds:
            updated,details=aligned_start(old,data,seed);aligned.append(updated);alignments.append(details)
        seeds=aligned
    obj=make_objective(data,meta,arm);records=[]
    def fitted(stage,seed,point,budget,fixed=False):
        r=fit(obj,feasible_start(obj,seed,20.,arm),point,budget,fixed,radius_km=4.)
        r['stage']=stage;records.append(r);return r
    # Equal two roof initializations and three spatial starts in all four arms.
    roofs=[fitted(f'roof-{i}',seed,[0.,0.],BUDGET['roof'],True) for i,seed in enumerate(seeds)]
    roof=min(roofs,key=lambda r:r['objective'])
    ring=[]
    for i,angle in enumerate(np.arange(4)*np.pi/2):
        point=3.2*np.array([np.cos(angle),np.sin(angle)])
        ring.append(fitted(f'probe-{i}',roof,point,BUDGET['probe'],True))
    for i,seed in enumerate([roof,seeds[1],min(ring,key=lambda r:r['objective'])]):
        fitted(f'search-{i}',seed,seed['point_km'],BUDGET['search'])
    best=best_record(records);fitted('polish',best,best['point_km'],BUDGET['polish'])
    best=best_record(records);obj.base.deadline=float('inf')
    score,_=obj.evaluate(np.asarray(best['vector']));like=obj.likelihood.last_result
    from render_leave_one_satellite_out import check_stationarity
    audited,kkt=check_stationarity(obj,best,4.)
    assert abs(score-audited)<1e-7 and abs(score-best['objective'])<1e-7
    penalty,_=obj.base.penalty(np.asarray(best['vector'])[:obj.size])
    pred,visible=obj.base.predict(np.asarray(best['vector'])[:obj.size])
    pred+=(obj.features@np.asarray(best['vector'])[obj.size:])[:,None]
    indices=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in data.owners]);rows=np.arange(len(indices))
    residual=(data.measured-pred[rows,indices]+obj.likelihood.alias_hz/2)%obj.likelihood.alias_hz-obj.likelihood.alias_hz/2
    owner_probability=like['row_association_probability'][rows,indices]
    result=dict(scope=__doc__,scan=scan,arm=arm,variant=variant,input_sha256=meta['input_sha256'],
        bank_receipt_sha256=digest(OUT/scan/'bank.json'),bank_states_sha256=bank['states_sha256'],
        input_source_sha256=digest(source),implementation_sha256=digest(Path(__file__)),
        fit_original_rows=data.original_rows,evaluation_original_rows=data.original_rows,heldout_original_rows=[],
        numbers=data.numbers,windows=len(data.times),maximum_budgets_s=BUDGET,roof_starts=2,spatial_starts=3,
        radius_km=4.,total_timing_bound_s=20.,alignment_diagnostics=alignments,
        roof=roof,best=best,records=records,objective=score,data_nll=score-penalty,timing_prior_nll=penalty,
        distance_m=1000*np.linalg.norm(best['point_km']),converged=bool(best['success'] and not best['fixed_location']),
        boundary=bool(np.linalg.norm(best['point_km'])>=3.9999),score_error=audited-best['objective'],kkt=kkt,
        strong_soft_windows=int(sum(np.max(like['row_association_probability'],axis=1)>.5)),
        strong_original_owner_windows=int(sum(owner_probability>.5)),owner_rms_hz=float(np.sqrt(np.mean(residual**2))),
        owner_median_absolute_residual_hz=float(np.median(abs(residual))),
        original_epoch_median_age_hours=bank['summary']['median_original_epoch_age_h'],
        selected_epoch_median_after_hours=bank['summary']['median_selected_epoch_after_scan_h'],
        changed_satellites=bank['summary']['changed'],fallback_satellites=bank['summary']['fallback'])
    assert max(abs(np.asarray(best['parameters'])[6:]))<=20.+1e-7
    target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
    print('POST-SCAN FIT',scan,arm,variant,round(result['distance_m']),best['status'],flush=True)
    return str(target)


def render():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows=[json.loads((OUT/s/f'{a}-{v}.json').read_text()) for s in SCANS for a in ARMS for v in VARIANTS]
    keys=['scan','arm','variant','windows','distance_m','converged','boundary','objective','data_nll','timing_prior_nll',
          'strong_soft_windows','strong_original_owner_windows','owner_rms_hz','owner_median_absolute_residual_hz',
          'original_epoch_median_age_hours','selected_epoch_median_after_hours','changed_satellites','fallback_satellites','kkt']
    with (OUT/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(rows)
    fig,axes=plt.subplots(2,1,figsize=(15,9),sharex=True,sharey=True)
    for ax,arm in zip(axes,ARMS):
        for i,scan in enumerate(SCANS):
            pair=[next(r for r in rows if (r['scan'],r['arm'],r['variant'])==(scan,arm,v)) for v in VARIANTS]
            ax.plot([i-.12,i+.12],[r['distance_m'] for r in pair],c='.65',lw=1)
            for dx,r,color,label in zip([-.12,.12],pair,['#888888','#0072b2'],['Original TLEs','Nearest post-scan epochs']):
                ax.scatter(i+dx,r['distance_m'],c=color,s=45,marker='^' if r['boundary'] else 'o',label=label if i==0 else None)
                if not r['converged']:ax.scatter(i+dx,r['distance_m'],marker='x',c='black',s=75)
            ax.annotate(f"{pair[1]['distance_m']:.0f}",(i+.12,pair[1]['distance_m']),xytext=(0,9),textcoords='offset points',ha='center',fontsize=9)
        values=[[r['distance_m'] for r in rows if r['arm']==arm and r['variant']==v] for v in VARIANTS]
        ax.set_title(('Fitted c' if arm=='fitted-c' else 'c = 0')+f' · median {np.median(values[0]):.0f} → {np.median(values[1]):.0f} m')
        ax.axhline(1000,c='.4',ls='--');ax.axhline(4000,c='.5',ls=':');ax.set_ylim(0,4480)
        ax.set_ylabel('Best-found position error (m)');ax.grid(axis='y',alpha=.18)
    axes[0].legend(loc='upper left',fontsize=9);axes[1].set_xticks(range(16),SCANS)
    fig.suptitle('Does backward propagation from post-scan TLEs reduce the position bias?',fontsize=17)
    fig.text(.5,.013,'Same associated top-one windows, satellite IDs, finite-set likelihood, timing priors and ±20 s timing bounds. Independent 4 km searches.\n'
        'Archived RX baseline unchanged; all position/nuisance fits use all retained windows. RF arms and TLE variants have matched search budgets.\n'
        'Epoch-only retrospective selection (≤24 h after scan); 13 unavailable post-scan elements retain originals. × = unconverged; triangles = boundary.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.11,1,.95));fig.savefig(OUT/'position-comparison.png',dpi=165);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--render-only',action='store_true');args=parser.parse_args()
    if not args.render_only:
        with ProcessPoolExecutor(max_workers=4) as pool:
            for f in as_completed([pool.submit(run,(s,a,v)) for s in SCANS for a in ARMS for v in VARIANTS]):f.result()
    render()
