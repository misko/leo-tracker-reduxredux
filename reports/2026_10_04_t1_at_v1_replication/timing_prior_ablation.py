"""All-window N01--N16 prior ablation; fixed original orbit/RX inputs.

Compare the original timing prior, Gaussian standard deviations multiplied by
three, and data-only fitting (no timing penalty). All retain the same +/-20 s
total timing, +/-10 s common timing and 4 km position bounds. No position prior,
data deletion, identity reselection, held-out fit, or per-scan truth-based choice.
This isolates localization regularization; upstream fold-derived RX baseline
is deliberately unchanged. Independent scans, matched fitted-c / c=0 arms.
"""
import argparse
import csv
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
from leave_one_satellite_out import load, HERE
from subset_positions import enable_research_model, serial
from timing_bound_comparison import feasible_start, digest
from convergence_fisher import fit
from resume_position_convergence import best_record

enable_research_model()
from timing_model import TimingObjective
from rf_calibration_diagnostic import CalibrationObjective
from audit_post_scan_tle import diagnostics
from render_leave_one_satellite_out import check_stationarity

OUT=HERE/'timing-prior-ablation'
SOURCE=HERE/'post-scan-tle-localization/polished'
SCANS=tuple(f'N{i:02}' for i in range(1,17))
ARMS=('fitted-c','zero-c')
PRECISIONS={'original':1., 'sigma-x3':1./9., 'data-only':0.}
BUDGET=dict(roof=4., probe=.3, search=4., polish=6.)


class ScaledTimingObjective(TimingObjective):
    def __init__(self,*args,prior_precision=1.,**kwargs):
        if not np.isfinite(prior_precision) or prior_precision<0:
            raise ValueError('Timing prior precision must be finite and nonnegative')
        self.prior_precision=float(prior_precision)
        super().__init__(*args,**kwargs)

    def penalty(self,vector):
        value,gradient=super().penalty(vector)
        return self.prior_precision*value,self.prior_precision*gradient


class PriorObjective(CalibrationObjective):
    def __init__(self,data,center,arm,precision):
        satellites=np.arange(len(data.numbers))
        super().__init__(data,data.initial,satellites,False,60.)
        self.base=ScaledTimingObjective(data,data.initial,satellites,self.likelihood,200.,prior_precision=precision)
        self.center=center;self.features=((data.rf-center)/1e9)[:,None]
        self.likelihood.features=self.features
        self.base.minimum_shift_s=max(self.base.minimum_shift_s,-20.)
        self.base.maximum_shift_s=min(self.base.maximum_shift_s,20.)
        if arm=='zero-c':self.bounds[-1]=(0.,0.)
        elif arm!='fitted-c':raise ValueError('Unknown RF arm')

    def curvature(self,vector):
        h=super().curvature(vector)
        # The legacy Fisher helper hardcodes the original penalty precision.
        # Change it as well as the objective/gradient: no hidden old regularizer.
        adjustment=self.base.prior_precision-1.
        h[6,6]+=adjustment*.01
        indices=np.arange(7,self.size)
        h[indices,indices]+=adjustment
        return h


def reprice(obj,record):
    obj.base.deadline=float('inf')
    score,kkt=check_stationarity(obj,record,4.)
    return dict(record,objective=score,kkt_residual=kkt,success=bool(kkt<=1e-3),
                stage='re-evaluated-common-seed',status='seed_repriced')


def run(task):
    scan,arm,mode=task;target=OUT/f'{scan}-{arm}-{mode}.json'
    if target.exists():return str(target)
    d,meta,_=load(scan);source=SOURCE/scan/f'{arm}-original.json';previous=json.loads(source.read_text())
    assert previous['input_sha256']==meta['input_sha256']
    obj=PriorObjective(d,meta['rf_center_hz'],arm,PRECISIONS[mode])
    seed=reprice(obj,previous['best']);records=[seed]
    def fitted(stage,record,point,budget,fixed=False):
        r=fit(obj,feasible_start(obj,record,20.,arm),point,budget,fixed,radius_km=4.)
        r['stage']=stage;records.append(r);return r
    roof=fitted('roof',seed,[0.,0.],BUDGET['roof'],True)
    ring=[]
    for i,angle in enumerate(np.arange(4)*np.pi/2):
        point=3.2*np.array([np.cos(angle),np.sin(angle)])
        ring.append(fitted(f'probe-{i}',roof,point,BUDGET['probe'],True))
    for i,start in enumerate([roof,seed,min(ring,key=lambda r:r['objective'])]):
        fitted(f'search-{i}',start,start['point_km'],BUDGET['search'])
    start=best_record(records);fitted('polish',start,start['point_km'],BUDGET['polish'])
    best=best_record(records);obj.base.deadline=float('inf');metrics=diagnostics(obj,d,best)
    assert metrics['objective']<=seed['objective']+1e-7
    assert np.max(abs(np.asarray(best['parameters'])[6:]))<=20.+1e-7
    assert np.linalg.norm(best['point_km'])<=4.+1e-7
    result=dict(scope=__doc__,scan=scan,arm=arm,mode=mode,prior_precision=PRECISIONS[mode],
        relative_timing_sigma_s=None if mode=='data-only' else (3. if mode=='sigma-x3' else 1.),
        common_timing_sigma_s=None if mode=='data-only' else (30. if mode=='sigma-x3' else 10.),
        windows=len(d.times),numbers=d.numbers,input_sha256=meta['input_sha256'],source_sha256=digest(source),
        implementation_sha256=digest(Path(__file__)),fit_original_rows=d.original_rows,
        evaluation_original_rows=d.original_rows,heldout_original_rows=[],maximum_budgets_s=BUDGET,
        radius_km=4.,total_timing_bound_s=20.,common_timing_bound_s=10.,
        roof=roof,best=best,records=records,baseline_distance_m=previous['distance_m'],
        baseline_data_nll=previous['data_nll'],baseline_timing_prior_nll=previous['timing_prior_nll'],**metrics)
    target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
    print('PRIOR ABLATION',scan,arm,mode,round(result['distance_m']),best['status'],result['kkt'],flush=True)
    return str(target)


def render():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows=[json.loads((OUT/f'{s}-{a}-{m}.json').read_text()) for s in SCANS for a in ARMS for m in PRECISIONS]
    keys=['scan','arm','mode','windows','distance_m','converged','boundary','objective','data_nll','timing_prior_nll',
          'posterior_weighted_residual_rms_hz','strong_soft_windows','strong_changed_owner_windows','kkt']
    with (OUT/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(rows)
    lookup={(r['scan'],r['arm'],r['mode']):r for r in rows}
    fig,axes=plt.subplots(2,1,figsize=(16,9),sharex=True,sharey=True)
    styles=[('original','Original Gaussian priors','#888888',-.2),
            ('sigma-x3','Timing prior σ × 3','#0072b2',0.),('data-only','No timing penalty','#d55e00',.2)]
    for ax,arm in zip(axes,ARMS):
        medians=[]
        for mode,label,color,dx in styles:
            values=[]
            for i,scan in enumerate(SCANS):
                r=lookup[scan,arm,mode];values.append(r['distance_m'])
                ax.scatter(i+dx,r['distance_m'],c=color,s=45,marker='^' if r['boundary'] else 'o',label=label if i==0 else None)
                if not r['converged']:ax.scatter(i+dx,r['distance_m'],c='black',marker='x',s=75)
            medians.append(f'{np.median(values):.0f}')
        ax.set_title(('Fitted c' if arm=='fitted-c' else 'c = 0')+' · median error: '+' / '.join(medians)+' m')
        ax.axhline(1000,c='.4',ls='--');ax.axhline(4000,c='.5',ls=':');ax.set_ylim(0,4430)
        ax.set_ylabel('Best-found position error (m)');ax.grid(axis='y',alpha=.18)
    axes[0].legend(loc='upper left',fontsize=9);axes[1].set_xticks(range(16),SCANS)
    fig.suptitle('How much of the position bias is driven by timing regularization?',fontsize=17)
    fig.text(.5,.018,'Same original TLEs, associated top-one windows, satellite bank, frozen RX baseline and search budgets. All retained windows fitted; no held-outs.\n'
        'Original σ: 1 s satellite-relative / 10 s common. Hard bounds stay ±20 s total / ±10 s common; independent 4 km position searches.\n'
        '× = unconverged; triangles = boundary. No position-truth prior or per-scan method selection; local searches are not global certificates.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.12,1,.95));fig.savefig(OUT/'position-comparison.png',dpi=165);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--render-only',action='store_true');args=parser.parse_args()
    OUT.mkdir(exist_ok=True)
    if not args.render_only:
        with ProcessPoolExecutor(max_workers=4) as pool:
            for f in as_completed([pool.submit(run,(s,a,m)) for s in SCANS for a in ARMS for m in PRECISIONS]):f.result()
    render()
