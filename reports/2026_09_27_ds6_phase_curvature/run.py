"""Shared phase curvature with unconstrained source intercepts."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent


def wrap(x):return np.angle(np.exp(1j*x))


def fit(t,z,s,bound):
    modes=np.unique(s);freq=np.linspace(-375,375,151);chirp=np.linspace(-bound,bound,21) if bound else np.array([0.])
    f,q=np.meshgrid(freq,chirp,indexing='ij');f=f.ravel();q=q.ravel();score=np.zeros(len(f))
    for label in modes:
        take=s==label;score+=abs(np.exp(-1j*(2*np.pi*f[:,None]*t[take]+np.pi*q[:,None]*t[take]**2))@z[take])
    def loss(p):
        rot=z*np.exp(-1j*(2*np.pi*p[0]*100*t+np.pi*p[1]*10000*t*t))
        return -sum(abs(rot[s==m].sum()) for m in modes)
    candidates=[]
    for i in np.argsort(score)[-3:]:
        start=np.array([f[i]/100,q[i]/10000]);candidates.append((loss(start),start,True))
        opt=minimize(loss,start,bounds=[(-3.75,3.75),(-bound/10000,bound/10000)],method='L-BFGS-B',options={'ftol':1e-14,'gtol':1e-9,'maxiter':300})
        candidates.append((float(opt.fun),opt.x,bool(opt.success)))
    cost,p,success=min(candidates,key=lambda x:x[0]);rate=p[0]*100;curvature=p[1]*10000
    rot=z*np.exp(-1j*(2*np.pi*rate*t+np.pi*curvature*t*t));intercepts={int(m):float(np.angle(rot[s==m].sum())) for m in modes}
    return dict(rate_hz=float(rate),chirp_hz_per_s=float(curvature),phases_rad=intercepts,objective=float(cost),optimizer_success=success,
                curvature_boundary=bool(bound and abs(curvature)>=.999*bound))


def extract(w,part):
    d=w['data'][part];return np.array(d['t']),np.array(d['z']['real'])+1j*np.array(d['z']['imag']),np.array(d['s'])


def evaluate(model,t,z,s):
    rot=z*np.exp(-1j*(2*np.pi*model['rate_hz']*t+np.pi*model['chirp_hz_per_s']*t*t))
    phases={int(m):float(np.angle(rot[s==m].sum())) for m in np.unique(s)}
    errors=wrap(np.angle(rot)-np.array([model['phases_rad'][int(m)] for m in s]))
    return dict(errors_rad=errors.tolist(),phase_dd_rad=float(wrap(phases[1]-phases[-1])),
                training_dd_rad=float(wrap(model['phases_rad'][1]-model['phases_rad'][-1])))


def main():
    src=ROOT/'2026_09_27_ds6_dwell_phase';source=src/'results.json';old=json.loads(source.read_text());arms={'linear':0.,'curvature_5000':5000.,'curvature_50000':50000.}
    paths={r['session_id']:src/(r['session_id']+'-frames.json') for r in old['results']}
    protocol=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),frames_sha256={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()},
        arms_chirp_bounds_hz_per_s=arms,rate_bounds_hz=[-375,375],
        model='phi_source + 2*pi*f*t + pi*chirp*t^2; shared frequency and chirp, independent source intercepts',
        validation='All original qualified windows; only fitting phasors estimate parameters, evaluation phasors score. No arm selection by held score.',
        scope='Post-result within-window diagnostic on ten development dwells; not new scans, cross-retune calibration, or geographic validation')
    pp=HERE/'protocol.json';pp.write_text(json.dumps(protocol,indent=2)+'\n');rows=[]
    for row in old['results']:
        sid=row['session_id'];windows=json.loads(paths[sid].read_text());out=dict(session_id=sid,visit=row['visit'],windows=[],arms={})
        for i,w in enumerate(windows):
            if not w['result']['both_qualified']:continue
            record=dict(window=i,midpoint_s=w['midpoint'],arms={})
            for name,bound in arms.items():
                model=fit(*extract(w,'fit'),bound);ev=evaluate(model,*extract(w,'evaluation'));record['arms'][name]=dict(model=model,**ev)
            out['windows'].append(record)
        for name in arms:
            rr=[w['arms'][name] for w in out['windows']]
            if not rr:continue
            errors=np.concatenate([r['errors_rad'] for r in rr]);dd=np.array([r['phase_dd_rad'] for r in rr])
            out['arms'][name]=dict(held_pilot_rms_deg=float(np.degrees(np.sqrt(np.mean(errors**2)))),held_count=len(errors),
                within_dwell_R=float(abs(np.exp(1j*dd).mean())),mean_dd_rad=float(np.angle(np.exp(1j*dd).mean())),
                fit_evaluation_dd_rms_deg=float(np.degrees(np.sqrt(np.mean([wrap(r['phase_dd_rad']-r['training_dd_rad'])**2 for r in rr])))),
                boundary_windows=sum(r['model']['curvature_boundary'] for r in rr))
        if not out['windows']:out['unavailable_reason']='No original jointly qualified window'
        rows.append(out)
    result=dict(complete=True,protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),rows=rows)
    (HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n');valid=[r for r in rows if r['windows']]
    fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True);x=np.arange(len(valid))
    for i,name in enumerate(arms):
        axes[0].bar(x+(i-1)*.25,[r['arms'][name]['held_pilot_rms_deg'] for r in valid],.25,label=name)
        axes[1].plot(x,[r['arms'][name]['within_dwell_R'] for r in valid],'o-',label=name)
    axes[0].set_ylabel('Held pilot RMS (degrees)');axes[0].legend();axes[1].set_ylabel('Within-dwell DD concentration R');axes[1].set_ylim(0,1.05);axes[1].set_xticks(x,[r['session_id'][-8:] for r in valid],rotation=25);fig.suptitle('DS6 shared phase curvature: held samples and source-difference stability');fig.tight_layout();fig.savefig(HERE/'curvature.png',dpi=180)
    print(json.dumps([dict(session_id=r['session_id'],windows=len(r['windows']),arms=r['arms']) for r in rows],indent=2))


if __name__=='__main__':main()
