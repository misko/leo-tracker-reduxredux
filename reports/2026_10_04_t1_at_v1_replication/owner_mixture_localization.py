"""Association-conditioned top-one likelihood diagnostic for all N01--N16.

Unlike the multiplet finite-set loss, condition on the T1-AT selected satellite
for each retained window. Use a Gaussian/uniform contamination model and fit
one noise scale and inlier fraction to every scan's full associated data.
No new fit/evaluation splits, row deletions, position priors, or choices based on
position truth. Original associations, fold-derived receiver baseline, orbit
bank and timing priors stay fixed to isolate the localization likelihood.
This is conditional inference, not independent satellite-identity validation.
"""
import argparse
import csv
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from leave_one_satellite_out import load,HERE
from subset_positions import enable_research_model,serial
from timing_bound_comparison import feasible_start,digest
from convergence_fisher import fit
from resume_position_convergence import best_record

enable_research_model()
from rf_calibration_diagnostic import CalibrationObjective
from soft_solvers import _fisher_system

SOURCE=HERE/'timing-bound-10s-vs-20s/cross-start-polish'
OUT=HERE/'owner-mixture-localization'
SCANS=tuple(f'N{i:02}' for i in range(1,17))
ARMS=('fitted-c','zero-c')
BUDGET=dict(roof=8.,probe=.7,search=8.,polish=8.)
ALIAS=2500000./11.


def logistic(z):return 1./(1.+np.exp(-z))


class OwnerLikelihood:
    def __init__(self,measured,group,owners,features):
        self.measured=np.asarray(measured);self.group=np.asarray(group)
        self.owners=np.asarray(owners,int);self.features=features
        if len(np.unique(self.group))!=len(self.group):
            raise ValueError('Owner likelihood requires exactly one candidate per window')
        if not (self.measured.shape==self.group.shape==self.owners.shape):
            raise ValueError('Mismatched observations/owners')
        self.order=np.argsort(self.group);self.alias_hz=ALIAS
        self.coefficients=np.zeros(1);self.sigma_hz=200.;self.inlier_probability=.95

    def evaluate(self,predicted,visible,**options):
        predicted=np.asarray(predicted);visible=np.asarray(visible,bool)
        if predicted.shape!=visible.shape or len(predicted)!=len(self.measured):
            raise ValueError('Prediction/visibility mismatch')
        row=np.arange(len(self.measured));owner=self.owners
        if np.any(owner<0) or np.any(owner>=predicted.shape[1]):raise ValueError('Unknown owner')
        p=self.inlier_probability;sigma=self.sigma_hz
        if not 0<p<1 or not 19.99999999<=sigma<=600.000001:raise ValueError('Invalid mixture parameters')
        e=(self.measured-predicted[row,owner]-(self.features@self.coefficients)+ALIAS/2)%ALIAS-ALIAS/2
        logsignal=np.log(p)-np.log(sigma)-.5*np.log(2*np.pi)-.5*(e/sigma)**2
        logclutter=np.log1p(-p)-np.log(ALIAS)
        logdensity=np.logaddexp(logsignal,logclutter)
        w=np.exp(logsignal-logdensity)
        valid=visible[row,owner]
        # Invisible owners cannot explain the retained observation: uniform
        # contamination only, with no noise/inlier parameter evidence.
        logdensity=np.where(valid,logdensity,-np.log(ALIAS));w=np.where(valid,w,0.)
        gradient=np.zeros_like(predicted);gradient[row,owner]=w*e/sigma**2
        posterior=np.zeros_like(predicted);posterior[row,owner]=w
        self.last_result=dict(total_log_likelihood=float(logdensity.sum()),
            log_likelihood=logdensity[self.order],group_values=self.group[self.order],
            row_association_probability=posterior,prediction_gradient=gradient,
            inlier_weight=w,residual_hz=e,owner_visible=valid,
            log_sigma_nll_gradient=float(np.sum(w*(1-(e/sigma)**2))),
            logit_inlier_nll_gradient=float(np.sum(np.where(valid,p-w,0.))))
        return self.last_result


class OwnerObjective(CalibrationObjective):
    def __init__(self,data,center,arm,learn_noise=True):
        super().__init__(data,data.initial,np.arange(len(data.numbers)),False,60.)
        self.features=((data.rf-center)/1e9)[:,None];self.center=center
        owner=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in data.owners])
        self.likelihood=OwnerLikelihood(data.measured,data.group,owner,self.features)
        self.base.likelihood=self.likelihood
        self.initial=np.r_[self.initial,np.log(200.),np.log(.95/.05)]
        self.bounds=self.bounds+[(np.log(20.),np.log(600.)),(np.log(.01/.99),np.log(.9999/.0001))]
        self.scale=np.r_[self.scale,1.,1.]
        if arm=='zero-c':self.bounds[self.size]=(0.,0.)
        elif arm!='fitted-c':raise ValueError('Unknown RF arm')
        if not learn_noise:
            self.bounds[-2:]=[(self.initial[-2],self.initial[-2]),(self.initial[-1],self.initial[-1])]
        self.base.minimum_shift_s=max(self.base.minimum_shift_s,-20.)
        self.base.maximum_shift_s=min(self.base.maximum_shift_s,20.)

    def evaluate(self,v):
        self.likelihood.coefficients=np.asarray(v[self.size:self.size+1])
        self.likelihood.sigma_hz=self.base.sigma_hz=float(np.exp(v[-2]))
        self.likelihood.inlier_probability=float(logistic(v[-1]))
        value,g=self.base.evaluate(np.asarray(v[:self.size]))
        if self.base.last is None:return value,np.r_[g,np.zeros(3)]
        r=self.likelihood.last_result
        cgradient=float(self.features[:,0]@(-r['prediction_gradient'].sum(axis=1)))
        return value,np.r_[g,cgradient,r['log_sigma_nll_gradient'],r['logit_inlier_nll_gradient']]

    def curvature(self,v):
        # Complete-data Fisher majorizer. Mean and log-scale/logit blocks are
        # orthogonal in expectation; actual objective checks every trial step.
        h=np.zeros((len(v),len(v)))
        h[:self.size,:self.size]=_fisher_system(self.base,v[:self.size],self.base.last)[0]
        _,_,jac=self.base.predict(v[:self.size],with_jacobian=True)
        r=self.likelihood.last_result
        weights=r['row_association_probability']/self.base.sigma_hz**2
        physical=jac.transpose_multiply((weights*self.features).ravel())
        cross=self.base.vector_gradient(physical,v[:self.size])
        h[:self.size,self.size]=cross;h[self.size,:self.size]=cross
        h[self.size,self.size]=np.sum(weights.sum(axis=1)*self.features[:,0]**2)
        h[-2,-2]=max(1e-8,2.*r['inlier_weight'].sum())
        p=self.likelihood.inlier_probability
        h[-1,-1]=max(1e-8,r['owner_visible'].sum()*p*(1-p))
        return h


def run(task):
    scan,arm,learn_noise=task;mode='learned-noise' if learn_noise else 'fixed-noise'
    target=OUT/f'{scan}-{arm}-{mode}.json'
    if target.exists():return str(target)
    data,meta,old=load(scan)
    source=SOURCE/f'{scan}-{arm}-20s.json';previous=json.loads(source.read_text())
    assert previous['input_sha256']==meta['input_sha256']
    obj=OwnerObjective(data,meta['rf_center_hz'],arm,learn_noise)
    records=[]
    def fitted(stage,seed,point,budget,fixed=False):
        start=feasible_start(obj,seed,20.,arm)
        start=np.r_[start,np.log(seed.get('sigma_hz',200.)),seed.get('logit_inlier',np.log(19.))]
        r=fit(obj,start,point,budget,fixed,radius_km=4.)
        r.update(stage=stage,coefficient=r['vector'][obj.size],sigma_hz=np.exp(r['vector'][-2]),
                 logit_inlier=r['vector'][-1],inlier_probability=logistic(r['vector'][-1]))
        records.append(r);return r
    roof=fitted('roof',previous['best'],[0.,0.],BUDGET['roof'],True)
    ring=[]
    for i,angle in enumerate(np.arange(4)*np.pi/2):
        point=3.2*np.array([np.cos(angle),np.sin(angle)])
        ring.append(fitted(f'probe-{i}',roof,point,BUDGET['probe'],True))
    seeds=[roof,previous['best'],min(ring,key=lambda r:r['objective'])]
    for i,seed in enumerate(seeds):fitted(f'search-{i}',seed,seed['point_km'],BUDGET['search'])
    best=best_record(records)
    fitted('polish',best,best['point_km'],BUDGET['polish'])
    best=best_record(records);obj.base.deadline=float('inf')
    value,_=obj.evaluate(np.asarray(best['vector']));r=obj.likelihood.last_result
    from render_leave_one_satellite_out import check_stationarity
    score,kkt=check_stationarity(obj,best,4.)
    assert abs(score-value)<1e-7 and abs(kkt-best['kkt_residual'])<1e-7
    total=np.asarray(best['parameters'])[6:]
    assert max(abs(total))<=20.+1e-7
    result=dict(scope=__doc__,scan=scan,arm=arm,mode=mode,windows=len(data.times),numbers=data.numbers,
        input_sha256=meta['input_sha256'],source_sha256=digest(source),implementation_sha256=digest(Path(__file__)),
        fit_original_rows=data.original_rows,evaluation_original_rows=data.original_rows,heldout_original_rows=[],
        maximum_budgets_s=BUDGET,radius_km=4.,total_timing_bound_s=20.,
        prior_note='Unchanged common timing sigma 10 s, relative timing sigma 1 s; no positional or noise prior.',
        sigma_bounds_hz=[20.,600.],inlier_probability_bounds=[.01,.9999],
        best=best,roof=roof,records=records,objective=value,distance_m=1000*np.linalg.norm(best['point_km']),
        baseline_error_m=previous['distance_m'],baseline_converged=previous['converged'],
        converged=bool(best['success'] and not best['fixed_location']),boundary=np.linalg.norm(best['point_km'])>=3.9999,
        strong_owner_windows=int(sum(r['inlier_weight']>.5)),owner_visible_windows=int(sum(r['owner_visible'])),
        median_owner_absolute_residual_hz=float(np.median(abs(r['residual_hz']))),
        timing_prior_nll=obj.base.penalty(np.asarray(best['vector'])[:obj.size])[0],
        owner_rms_hz=float(np.sqrt(np.mean(r['residual_hz']**2))),score_error=score-value,kkt=kkt)
    target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
    print('OWNER MIXTURE',scan,arm,mode,round(result['distance_m']),best['status'],
          'sigma',round(best['sigma_hz'],1),'inlier',round(best['inlier_probability'],3),flush=True)
    return str(target)


def render():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows=[json.loads(p.read_text()) for p in sorted(OUT.glob('*-noise.json'))]
    keys=['scan','arm','mode','windows','distance_m','baseline_error_m','baseline_converged','converged','boundary',
          'strong_owner_windows','median_owner_absolute_residual_hz','owner_rms_hz','timing_prior_nll','kkt']
    with (OUT/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys+['sigma_hz','inlier_probability'],extrasaction='ignore');w.writeheader()
        for r in rows:w.writerow(dict(r,**{k:r['best'][k] for k in ('sigma_hz','inlier_probability')}))
    fig,axes=plt.subplots(2,1,figsize=(15,9),sharex=True,sharey=True)
    for ax,arm in zip(axes,ARMS):
        for i,scan in enumerate(SCANS):
            r=next((r for r in rows if (r['scan'],r['arm'],r['mode'])==(scan,arm,'learned-noise')),None)
            if r is None:continue
            fixed=next((v for v in rows if (v['scan'],v['arm'],v['mode'])==(scan,arm,'fixed-noise')),None)
            ax.plot([i-.19,i+.19],[r['baseline_error_m'],r['distance_m']],color='.75',lw=1)
            ax.scatter(i-.19,r['baseline_error_m'],c='.5',s=32,label='Previous finite-set loss' if i==0 else None)
            if fixed is not None:
                ax.scatter(i,fixed['distance_m'],c='#009e73',s=36,marker='^' if fixed['boundary'] else 's',label='Owner-conditioned, fixed noise' if i==0 else None)
                if not fixed['converged']:ax.scatter(i,fixed['distance_m'],marker='x',c='black',s=80)
            ax.scatter(i+.19,r['distance_m'],c='#0072b2',s=45,marker='^' if r['boundary'] else 'o',label='Owner-conditioned, learned noise' if i==0 else None)
            if not r['converged']:ax.scatter(i+.19,r['distance_m'],marker='x',c='black',s=80)
            if not r['baseline_converged']:ax.scatter(i-.19,r['baseline_error_m'],marker='x',c='black',s=65)
            ax.annotate(f"{r['distance_m']:.0f}",(i+.19,r['distance_m']),xytext=(0,9),textcoords='offset points',ha='center',fontsize=9)
        ax.axhline(1000,c='.4',ls='--');ax.axhline(4000,c='.6',ls=':');ax.set_ylim(0,4480)
        ax.set_ylabel('Best-found position error (m)');ax.set_title('Fitted c' if arm=='fitted-c' else 'c = 0');ax.grid(axis='y',alpha=.2)
    axes[0].legend(loc='upper left',fontsize=9);axes[1].set_xticks(range(16),SCANS)
    fig.suptitle('Does conditioning on the selected association and learning noise improve localization?',fontsize=17)
    fig.text(.5,.014,'All associated top-one windows retained in each position fit; archived fold-derived RX baseline unchanged. Independent 4 km searches; ±20 s timing.\n'
             'Fixed noise: 200 Hz / 95% inliers; learned noise: both estimated on all retained windows. Matched RF-arm inputs, priors and budgets.\n'
             '× = unconverged; triangle = new boundary solution. Best-found local fits, not global certificates; coverage counts are not changed.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.1,1,.95));fig.savefig(OUT/'position-comparison.png',dpi=165);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--scans',nargs='+',default=list(SCANS));parser.add_argument('--fixed-noise',action='store_true')
    parser.add_argument('--render-only',action='store_true');args=parser.parse_args()
    if not set(args.scans).issubset(SCANS):raise ValueError('Unknown scan')
    OUT.mkdir(exist_ok=True)
    if not args.render_only:
        with ProcessPoolExecutor(max_workers=3) as pool:
            jobs=[(s,a,not args.fixed_noise) for s in args.scans for a in ARMS]
            for f in as_completed([pool.submit(run,j) for j in jobs]):f.result()
    render()
