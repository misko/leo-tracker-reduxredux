"""Profile nonlinear receiver drift with position, with no calibration folds.

Matched N12/N15 diagnostic on the full-fixed-members observations. This retains
the associated-window input policy; 'full' does not mean adding unassociated
windows. Frozen and joint models use identical data, bank, likelihood, priors,
timing bounds, starts and maximum search budgets. No position prior is added.
"""
import argparse
import csv
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from full_data_calibration import OUT as SOURCE, ARMS, digest, serial
from subset_positions import enable_research_model
from timing_bound_comparison import feasible_start
from convergence_fisher import fit
from resume_position_convergence import best_record

enable_research_model()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'2026_10_03_ds13_coverage_goal'))
import receiver_spline
from rf_calibration_diagnostic import CalibrationObjective

OUT=SOURCE/'joint-receiver-drift'
SCANS=('N12','N15')
MODES=('frozen','joint')
BUDGET=dict(roof=12.,probe=1.,search=15.,polish=20.)


def spline_features(times, receiver):
    receiver=np.asarray(receiver)
    if not np.all(np.isin(receiver,[0,1])):
        raise ValueError('Unknown receiver')
    basis=receiver_spline.design(times)
    return np.column_stack([basis*(receiver==rx)[:,None] for rx in (0,1)])


def spline_prior(coefficients):
    beta=np.asarray(coefficients).reshape(2,9)
    gradient=beta@receiver_spline.PRECISION
    return .5*float(np.sum(beta*gradient)),gradient.ravel()


class JointReceiverObjective(CalibrationObjective):
    def __init__(self,data,center,beta,arm,mode):
        super().__init__(data,data.initial,np.arange(len(data.numbers)),False,60.)
        if mode not in MODES or arm not in ARMS:
            raise ValueError('Unknown mode or RF arm')
        self.center=center
        self.features=np.column_stack([(data.rf-center)/1e9,
                                       spline_features(data.times,data.receiver)])
        self.likelihood.features=self.features
        self.likelihood.coefficients=np.r_[0.,np.asarray(beta).ravel()]
        self.initial=np.r_[self.base.initial_vector,self.likelihood.coefficients]
        self.bounds=self.base.bounds+[(-5000.,5000.)]+[(None,None)]*18
        if arm=='zero-c':self.bounds[self.size]=(0.,0.)
        if mode=='frozen':
            self.bounds[self.size+1:]=[(float(v),float(v)) for v in np.asarray(beta).ravel()]
        self.scale=np.r_[self.scale[:self.size],1000.,np.full(18,50.)]
        self.base.minimum_shift_s=max(self.base.minimum_shift_s,-20.)
        self.base.maximum_shift_s=min(self.base.maximum_shift_s,20.)
        self.precision=np.zeros((19,19))
        self.precision[1:10,1:10]=receiver_spline.PRECISION
        self.precision[10:,10:]=receiver_spline.PRECISION

    def evaluate(self,vector):
        value,gradient=super().evaluate(vector)
        penalty,pg=spline_prior(vector[self.size+1:])
        gradient[self.size+1:]+=pg
        return value+penalty,gradient

    def curvature(self,vector):
        hessian=super().curvature(vector)
        hessian[self.size:,self.size:]+=self.precision
        return hessian


def prepare(scan):
    source=SOURCE/scan/'full-fixed-members-input.npz'
    with np.load(source) as z:
        data=SimpleNamespace(**{k:z[k].copy() for k in z.files})
    calibration=json.loads((SOURCE/scan/'calibration.json').read_text())
    beta=np.asarray(calibration['correction_knots_hz'])@receiver_spline.NULL
    correction=spline_features(data.times,data.receiver)@beta.ravel()
    # Undo only the frozen nonlinear part; receiver lines remain an equivalent
    # fixed reference plus freely fitted lines, exactly as in the control.
    data.measured=data.measured+correction
    data.fixed_receiver_hz=data.fixed_receiver_hz-correction
    previous=json.loads((SOURCE/scan/'full-fixed-members-position.json').read_text())
    return data,calibration['rf_center_hz'],beta,previous,source


def run(task):
    scan,arm,mode=task
    target=OUT/f'{scan}-{arm}-{mode}.json'
    if target.exists():return str(target)
    data,center,beta,previous,source=prepare(scan)
    obj=JointReceiverObjective(data,center,beta,arm,mode)
    old=previous['arms'][arm];records=[]

    def fitted(stage,seed,point,budget,fixed=False):
        start=feasible_start(obj,seed,20.,arm)
        start=np.r_[start,seed.get('spline_coefficients',beta.ravel())]
        r=fit(obj,start,point,budget,fixed,radius_km=4.)
        # The generic fitter assumes its last coefficient is c; here c comes
        # before the eighteen spline coefficients. Correct the receipt explicitly.
        r['coefficient']=r['vector'][obj.size]
        r['spline_coefficients']=r['vector'][obj.size+1:]
        r['stage']=stage;records.append(r)
        return r

    roof=fitted('roof',old['roof'],[0.,0.],BUDGET['roof'],True)
    probes=[]
    for i,angle in enumerate(np.arange(4)*np.pi/2):
        point=3.2*np.array([np.cos(angle),np.sin(angle)])
        probes.append(fitted(f'probe-{i}',roof,point,BUDGET['probe'],True))
    ring=min(probes,key=lambda r:r['objective'])
    for i,seed in enumerate([roof,old['best'],ring]):
        fitted(f'search-{i}',seed,seed['point_km'],BUDGET['search'])
    best=best_record(records)
    fitted('polish',best,best['point_km'],BUDGET['polish'])
    best=best_record(records)
    obj.base.deadline=float('inf')
    value,_=obj.evaluate(np.asarray(best['vector']))
    timing,_=obj.base.penalty(np.asarray(best['vector'])[:obj.size])
    spline,_=spline_prior(best['spline_coefficients'])
    probability=obj.likelihood.last_result['row_association_probability']
    from render_leave_one_satellite_out import check_stationarity
    score,kkt=check_stationarity(obj,best,4.)
    assert abs(score-best['objective'])<1e-7
    assert abs(kkt-best['kkt_residual'])<1e-7
    if mode=='frozen':
        np.testing.assert_allclose(best['spline_coefficients'],beta.ravel(),atol=1e-10)
        assert score<=old['best']['objective']+spline+1e-6
    assert max(abs(np.asarray(best['parameters'])[6:]))<=20.+1e-7
    result=dict(scope=__doc__,scan=scan,arm=arm,mode=mode,input_sha256=digest(source),
        implementation_sha256=digest(Path(__file__)),windows=len(data.times),numbers=data.numbers,
        fit_original_rows=data.original_rows,evaluation_original_rows=data.original_rows,heldout_original_rows=[],
        maximum_budgets_s=BUDGET,radius_km=4.,total_timing_bound_s=20.,
        spline_priors=dict(amplitude_sigma_hz=50.,second_difference_sigma_hz=25.,knot_spacing_s=30.),
        best=best,roof=roof,records=records,distance_m=1000*np.linalg.norm(best['point_km']),
        converged=bool(best['success'] and not best['fixed_location']),boundary=np.linalg.norm(best['point_km'])>=3.9999,
        objective=value,data_nll=value-timing-spline,timing_prior_nll=timing,spline_prior_nll=spline,
        strong_soft_windows=int(sum(np.max(probability,axis=1)>.5)),
        audit=dict(score_error=score-best['objective'],kkt=kkt))
    target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
    print('JOINT RX',scan,arm,mode,round(result['distance_m']),best['status'],flush=True)
    return str(target)


def render():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows=[json.loads((OUT/f'{s}-{a}-{m}.json').read_text()) for s in SCANS for a in ARMS for m in MODES]
    keys=['scan','arm','mode','windows','distance_m','converged','boundary','objective','data_nll',
          'timing_prior_nll','spline_prior_nll','strong_soft_windows']
    with (OUT/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(12,5),sharey=True)
    for ax,scan in zip(axes,SCANS):
        for arm,color in zip(ARMS,['#0072b2','#d55e00']):
            values=[next(r for r in rows if (r['scan'],r['arm'],r['mode'])==(scan,arm,m)) for m in MODES]
            ax.plot([0,1],[r['distance_m'] for r in values],color=color,marker='o',label='Fitted c' if arm=='fitted-c' else 'c = 0')
            for i,r in enumerate(values):
                ax.annotate(f"{r['distance_m']:.0f} m",(i,r['distance_m']),xytext=(0,10),textcoords='offset points',ha='center',color=color)
                if not r['converged']:ax.scatter(i,r['distance_m'],marker='x',c='black',s=100)
                if r['boundary']:ax.scatter(i,r['distance_m'],marker='^',c=color,s=100)
        ax.set_xticks([0,1],['Full-data drift\nfrozen before position','Full-data drift\nfitted jointly with position'])
        ax.set_xlim(-.35,1.35);ax.set_ylim(0,4450);ax.grid(alpha=.18);ax.set_title(scan)
        ax.axhline(1000,color='.5',ls=':');ax.axhline(4000,color='.5',ls=':')
    axes[0].set_ylabel('Best-found position error (m)');axes[0].legend()
    fig.suptitle('Does profiling receiver drift remove the position bias?',fontsize=17)
    fig.text(.5,.015,'Same associated top-one windows and satellite bank; no folds or held-out windows. Independent 4 km searches.\n'
             'Shared RX drift has 30 s knots with zero-centered 50 Hz amplitude / 25 Hz curvature priors. ±20 s satellite timing.\n'
             'In-sample conditional diagnostic; no positional prior. × = unconverged, triangle = boundary.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.15,1,.94));fig.savefig(OUT/'joint-drift-position-comparison.png',dpi=170);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--render-only',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if not args.render_only:
        with ProcessPoolExecutor(max_workers=2) as pool:
            list(pool.map(run,[(s,a,m) for s in SCANS for a in ARMS for m in MODES]))
    render()
