"""Marginal source-DD likelihood, integrating common phase and residual rate."""
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
from scipy.special import i0e,logsumexp
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('curvature',ROOT/'2026_09_27_ds6_phase_curvature/run.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def log_i0(x):return np.log(i0e(x))+abs(x)


def sums(t,z,s,f):
    return [np.exp(-2j*np.pi*f[:,None]*t[s==m])@z[s==m] for m in [-1,1]]


def evidence(data,kappa,f):
    t,z,s=data;a,b=sums(t,z,s,f);w=np.ones(len(f));w[[0,-1]]=.5;w/=w.sum()
    return float(logsumexp(log_i0(kappa*abs(a))+log_i0(kappa*abs(b))-len(t)*log_i0(kappa)+np.log(w)))


def posterior(data,kappa,f,delta):
    t,z,s=data;a,b=sums(t,z,s,f);w=np.ones(len(f));w[[0,-1]]=.5;w/=w.sum()
    # Integrate phi_A uniformly, with phi_B=phi_A+delta.
    logp=logsumexp(log_i0(kappa*abs(a[:,None]+b[:,None]*np.exp(-1j*delta[None,:])))-len(t)*log_i0(kappa)+np.log(w)[:,None],axis=0)
    probability=np.exp(logp-logsumexp(logp));mean=float(np.angle(probability@np.exp(1j*delta)))
    distance=abs(base.wrap(delta-mean));order=np.argsort(distance);radius=float(distance[order[np.searchsorted(np.cumsum(probability[order]),.95)]])
    return dict(probability=probability.tolist(),mean_dd_rad=mean,circular_R=float(abs(probability@np.exp(1j*delta))),credible95_radius_deg=float(np.degrees(radius)))


def main():
    src=ROOT/'2026_09_27_ds6_phase_curvature';sids=['scan-fw-c78fb2dba2465361','scan-fw-c7e37f65ae9e08b0'];paths={s:src/(s+'-frames.json') for s in sids};f=np.linspace(-375,375,751);delta=np.linspace(-np.pi,np.pi,720,endpoint=False)
    protocol=dict(source_hashes={s:hashlib.sha256(p.read_bytes()).hexdigest() for s,p in paths.items()},kappa=[4.,16.],frequency_prior_hz=[-375,375],frequency_nodes=len(f),phase_nodes=len(delta),
        model='Independent von Mises pilot errors at fixed concentration; common constant residual rate; independent uniform source intercepts',
        scope='All 75 qualified windows; training phasors determine posteriors, held phasors only evaluate predictive scores; fixed observer is not used; not a geographic result')
    pp=HERE/'protocol.json';pp.write_text(json.dumps(protocol,indent=2)+'\n');rows=[];audits=[]
    for sid,path in paths.items():
        records=json.loads(path.read_text());windows=[]
        for index,r in enumerate(records):
            w=r['frame'];train=base.extract(w,'fit');held=base.extract(w,'evaluation');all_=[np.concatenate([a,b]) for a,b in zip(train,held)];model=base.fit(*train,0);errors=np.array(base.evaluate(model,*held)['errors_rad'])
            out={k:r[k] for k in ['visit','group','start_ms']};out['arms']={}
            for kappa in protocol['kappa']:
                post=posterior(train,kappa,f,delta);post['held_log_predictive']=evidence(all_,kappa,f)-evidence(train,kappa,f)
                post['point_fit_held_log_score']=float(np.sum(kappa*np.cos(errors)-log_i0(kappa)));post['point_dd_rad']=float(base.wrap(model['phases_rad'][1]-model['phases_rad'][-1]));out['arms'][str(kappa)]=post
                if index==0:
                    fine=np.linspace(-375,375,1501);p2=posterior(train,kappa,fine,delta)
                    audits.append(dict(session_id=sid,kappa=kappa,max_probability_change=float(np.max(abs(np.array(post['probability'])-p2['probability']))),
                        held_score_change=float(evidence(all_,kappa,fine)-evidence(train,kappa,fine)-post['held_log_predictive'])))
            windows.append(out)
        rows.append(dict(session_id=sid,windows=windows))
    result=dict(complete=True,protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),phase_grid_rad=delta.tolist(),scans=rows,quadrature_audits=audits)
    (HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n');summary=[];fig,axes=plt.subplots(1,2,figsize=(11,4.5))
    for si,s in enumerate(rows):
        item=dict(session_id=s['session_id'],arms={})
        for ki,kappa in enumerate(protocol['kappa']):
            rr=[w['arms'][str(kappa)] for w in s['windows']];width=[a['credible95_radius_deg'] for a in rr];gain=sum(a['held_log_predictive']-a['point_fit_held_log_score'] for a in rr)
            item['arms'][str(kappa)]=dict(median_credible95_radius_deg=float(np.median(width)),min_radius_deg=min(width),max_radius_deg=max(width),held_score_gain=float(gain))
            axes[si].plot(width,'o',label=f'κ={kappa:g}',alpha=.7)
        axes[si].set_title(s['session_id'][-8:]);axes[si].set_xlabel('Qualified window, stored order');axes[si].set_ylabel('95% radius about circular mean (degrees)');axes[si].legend();summary.append(item)
    fig.suptitle('DS6 phase-DD uncertainty after marginalizing receiver rate\nModel-conditional intervals; no claim of physical coverage');fig.tight_layout();fig.savefig(HERE/'phase-widths.png',dpi=180)
    (HERE/'summary.json').write_text(json.dumps(dict(scans=summary,quadrature_audits=audits),indent=2)+'\n');print(json.dumps(summary,indent=2));print(json.dumps(audits,indent=2))


if __name__=='__main__':main()
