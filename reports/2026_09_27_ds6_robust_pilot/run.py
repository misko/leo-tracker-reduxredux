"""Circular contamination likelihood for shared-rate source phase fits."""
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import i0e
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('curvature',ROOT/'2026_09_27_ds6_phase_curvature/run.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def log_density(error,kappa,epsilon=.1):
    return np.logaddexp(np.log1p(-epsilon)+kappa*np.cos(error)-(np.log(i0e(kappa))+kappa),np.log(epsilon))


def fit(t,z,s,kappa):
    angle=np.angle(z);modes=np.unique(s);assert np.array_equal(modes,[-1,1])
    def loss(p):return -float(log_density(angle-(np.where(s==-1,p[1],p[2])+2*np.pi*100*p[0]*t),kappa).sum())
    starts=[]
    for f in np.linspace(-375,375,151):
        rot=z*np.exp(-2j*np.pi*f*t);p=np.array([f/100,*[np.angle(rot[s==m].sum()) for m in modes]])
        starts.append((loss(p),p))
    candidates=[]
    for cost,p in sorted(starts,key=lambda v:v[0])[:5]:
        candidates.append((cost,p,True));opt=minimize(loss,p,method='L-BFGS-B',bounds=[(-3.75,3.75),(None,None),(None,None)],options={'maxiter':300,'ftol':1e-13,'gtol':1e-8})
        candidates.append((float(opt.fun),opt.x,bool(opt.success)))
    cost,p,success=min(candidates,key=lambda v:v[0]);err=angle-(np.where(s==-1,p[1],p[2])+2*np.pi*100*p[0]*t)
    signal=np.log(.9)+kappa*np.cos(err)-(np.log(i0e(kappa))+kappa);responsibility=np.exp(signal-np.logaddexp(signal,np.log(.1)))
    return dict(rate_hz=float(p[0]*100),chirp_hz_per_s=0.,phases_rad={-1:float(base.wrap(p[1])),1:float(base.wrap(p[2]))},
        objective=cost,optimizer_success=success,inlier_probabilities=responsibility.tolist())


def main():
    src=ROOT/'2026_09_27_ds6_phase_curvature';sids=['scan-fw-c78fb2dba2465361','scan-fw-c7e37f65ae9e08b0'];paths={s:src/(s+'-frames.json') for s in sids}
    protocol=dict(source_hashes={s:hashlib.sha256(p.read_bytes()).hexdigest() for s,p in paths.items()},arms=dict(equal_weight=None,mixture_k4=4.,mixture_k16=16.),outlier_fraction=.1,
        selection='All 75 previously qualified windows; no pilot or window is removed from evaluation',
        fitting='Common residual rate and independent source phases; fit samples only; five training-ranked starts',
        scope='Exploratory cached-pilot diagnostic on two development scans; fixed mixture assumptions, not fitted phase reliability')
    pp=HERE/'protocol.json';pp.write_text(json.dumps(protocol,indent=2)+'\n');rows=[]
    for sid,path in paths.items():
        cache=json.loads(path.read_text());windows=[]
        for record in cache:
            w=record['frame'];out={k:record[k] for k in ['group','visit','start_ms']};out['arms']={}
            for name,kappa in protocol['arms'].items():
                model=base.fit(*base.extract(w,'fit'),0.) if kappa is None else fit(*base.extract(w,'fit'),kappa)
                ev=base.evaluate(model,*base.extract(w,'evaluation'));e=np.array(ev['errors_rad']);out['arms'][name]=dict(model=model,**ev,
                    common_k4_held_log_score=float(log_density(e,4.).sum()))
            windows.append(out)
        summary={}
        for arm in protocol['arms']:
            e=np.concatenate([w['arms'][arm]['errors_rad'] for w in windows]);dd=np.array([base.wrap(w['arms'][arm]['phase_dd_rad']-w['arms'][arm]['training_dd_rad']) for w in windows]);summary[arm]=dict(
                held_pilot_rms_deg=float(np.degrees(np.sqrt(np.mean(e**2)))),fit_evaluation_dd_rms_deg=float(np.degrees(np.sqrt(np.mean(dd**2)))),
                common_k4_held_log_score=float(sum(w['arms'][arm]['common_k4_held_log_score'] for w in windows)),
                low_inlier_fit_pilots=sum(sum(p<.5 for p in w['arms'][arm]['model'].get('inlier_probabilities',[])) for w in windows))
        rows.append(dict(session_id=sid,windows=windows,summary=summary))
    result=dict(complete=True,protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),scans=rows);(HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    fig,axes=plt.subplots(1,2,figsize=(11,4.5));names=list(protocol['arms'])
    for i,s in enumerate(rows):
        axes[0].bar(np.arange(3)+i*4,[s['summary'][a]['held_pilot_rms_deg'] for a in names],color=['gray','steelblue','darkorange']);axes[1].bar(np.arange(3)+i*4,[s['summary'][a]['common_k4_held_log_score']-s['summary']['equal_weight']['common_k4_held_log_score'] for a in names],color=['gray','steelblue','darkorange'])
    for ax in axes:ax.set_xticks([1,5],[s[-8:] for s in sids])
    axes[0].set_ylabel('Held pilot RMS (degrees)');axes[1].set_ylabel('Held log-score gain, common κ=4 scoring');fig.suptitle('DS6 robust pilot fits: gray equal-weight, blue κ=4, orange κ=16\nAll held samples retained; fixed 10% uniform contamination');fig.tight_layout();fig.savefig(HERE/'robust-pilots.png',dpi=180)
    print(json.dumps([dict(session_id=s['session_id'],summary=s['summary']) for s in rows],indent=2))


if __name__=='__main__':main()
