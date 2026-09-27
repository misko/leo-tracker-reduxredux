"""Full visible-pair receiver-delay test, fixed one-dwell concentration."""
import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
import numpy as np
from scipy.special import i0e,logsumexp
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states,REFERENCE_RF_HZ,LIGHT_KM_S
from leo.sky.frames import geodetic_to_ecef_km

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('pair_run',ROOT/'2026_09_27_ds6_pair_proposals/run.py')
pair=importlib.util.module_from_spec(spec);spec.loader.exec_module(pair)


def log_i0(x):return np.log(i0e(x))+abs(x)


def delay_scores(residual,df,delays,mask):
    """Fixed kappa=1 densities relative to uniform, observation axis last."""
    z=np.exp(1j*residual);rot=np.exp(-2j*np.pi*df[:,None]*delays[None,:])
    return (z[:,mask]@rot[mask]).real-mask.sum()*log_i0(1.),(z@rot).real-len(df)*log_i0(1.)


def offset_scores(residual,mask):
    z=np.exp(1j*residual)
    return log_i0(abs(z[:,mask].sum(axis=-1)))-mask.sum()*log_i0(1.),log_i0(abs(z.sum(axis=-1)))-len(mask)*log_i0(1.)


def combine(groups,weights):
    fields={k:sum(g[k] for g in groups) for k in ['train','phase_all','cfo_all']}
    prior=np.log(weights)[None,None,:]-np.log(fields['train'].shape[0]*fields['train'].shape[1])
    z=logsumexp(fields['train']+prior)
    return dict(training_log_evidence=float(z),held_phase=float(logsumexp(fields['phase_all']+prior)-z),
                held_cfo=float(logsumexp(fields['cfo_all']+prior)-z))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--points',type=int,default=101);args=ap.parse_args()
    assert args.points in [101,201]
    source_path=ROOT/'2026_09_27_ds6_differential_cfo/results.json';source=json.loads(source_path.read_text())
    base_path=ROOT/'2026_09_27_ds6_pair_proposals/protocol.json';base=json.loads(base_path.read_text());lat,lon=base['observer_from_other_scan_cfo']
    delays=np.linspace(-1e-5,1e-5,args.points);weights=np.ones(args.points);weights[[0,-1]]=.5;weights/=weights.sum()
    protocol=dict(source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),base_sha256=hashlib.sha256(base_path.read_bytes()).hexdigest(),
        observer=[lat,lon],delay_points=args.points,delay_prior_us=[-10,10],kappa=1.,
        scope='Full training-visible pairs; shared delay across two channels within each scan versus independent pair offsets; fixed observer; conditional on observed per-visit RX0 GLRT source separation',
        selection='All training-visible pairs, original visit masks; no phase or reference-position candidate selection',
        timing_s=base['timing_s'])
    pp=HERE/f'protocol-{args.points}.json';pp.write_text(json.dumps(protocol,indent=2)+'\n')
    receiver=geodetic_to_ecef_km(lat,lon,0);la,lo=np.radians([lat,lon]);east=np.array([-np.sin(lo),np.cos(lo),0.]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)])
    taus=np.array(base['timing_s']);results=[];started=time.monotonic()
    for scan in source['scans']:
        sid=scan['session_id'];planpath=ROOT/'2026_09_27_ds6_common_rate_validation'/(sid+'-plan.json');plan=json.loads(planpath.read_text());cat=pair.u.load_catalogue(plan)
        tracks={t['track_id']:t for t in plan['tracks']};indices=np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')]);prior=-2*np.log(len(indices));arms={k:[] for k in ['delay_geometry','delay_null','offset_geometry','offset_null']};inventory=[]
        for gi,group in enumerate(scan['groups']):
            paired=pair.dd.paired_observations(*[tracks[t] for t in group['track_ids']]);mask=paired['mask'];delta=paired['measured'][1]-paired['measured'][0];n=len(mask)
            obs=group['phase_observations'];times=np.array([o['time_s'] for o in obs]);pmask=np.array([o['train'] for o in obs]);y=np.array([o['phase'] for o in obs]);df=[]
            for o in obs:
                v=next(v for v in plan['selected'] if v['visit']==o['visit'] and v['group']==group['group'])
                assert [m['rx0_track_id'] for m in v['modes']]==group['track_ids']
                cf=[next(s['cfo_hz'] for s in m['seeds'] if s['receiver_id']==0) for m in v['modes']];df.append(cf[1]-cf[0])
            df=np.array(df);states=[]
            for mode in [0,1]:
                pred=[];proj=[];vis=[]
                for first in range(0,len(indices),256):
                    p,v,valid=propagate_candidate_states(cat,indices[first:first+256],plan['start_utc_ns'],np.r_[paired['source_times'][mode],times],taus)
                    direction=p-receiver;direction/=np.linalg.norm(direction,axis=-1,keepdims=True)
                    pred.append(-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(direction[:,:,:n]*v[:,:,:n],axis=-1));proj.append(direction[:,:,n:]@east);vis.append(np.any((direction[:,:,:n]@up)[...,mask]>=0,axis=-1))
                states.append(dict(pred=np.concatenate(pred),proj=np.concatenate(proj),vis=np.concatenate(vis)))
            stats={k:{f:np.full((2,len(taus),args.points if k.startswith('delay') else 1),-np.inf) for f in ['train','phase_all','cfo_all']} for k in arms};counts=[]
            a,b=states;factor=2*np.pi*.08*tracks[group['track_ids'][0]]['rf_hz']/299792458.
            for ti,tau in enumerate(taus):
                ia=np.flatnonzero(a['vis'][:,ti]);ib=np.flatnonzero(b['vis'][:,ti]);counts.append(len(ia)*len(ib))
                for first in range(0,len(ia),16):
                    aa=ia[first:first+16];res=(delta-(b['pred'][ib,ti][None,:,:]-a['pred'][aa,ti][:,None,:])).reshape(-1,n)
                    ct,cj=pair.u.robust_scores(res,mask,sigma=group['differential_scale_hz']);ct+=prior;cj+=prior
                    geom=(factor*(b['proj'][ib,ti][None,:,:]-a['proj'][aa,ti][:,None,:])).reshape(-1,len(y))
                    for si,sign in enumerate([-1,1]):
                        for name in arms:
                            r=y[None,:]-sign*geom if name.endswith('geometry') else y[None,:]
                            if name.startswith('delay'):ft,all_=delay_scores(r,df,delays,pmask)
                            else:
                                ft,all_=offset_scores(r,pmask);ft=ft[:,None];all_=all_[:,None]
                            for f,val in [('train',ct[:,None]+ft),('phase_all',ct[:,None]+all_),('cfo_all',cj[:,None]+ft)]:
                                stats[name][f][si,ti]=np.logaddexp(stats[name][f][si,ti],logsumexp(val,axis=0))
                print(sid,gi,tau,round(time.monotonic()-started,1),flush=True)
            for name in arms:arms[name].append(stats[name])
            inventory.append(dict(group=group['group'],pair_counts=counts,df_hz=df.tolist(),visits=[o['visit'] for o in obs]))
        results.append(dict(session_id=sid,plan_sha256=hashlib.sha256(planpath.read_bytes()).hexdigest(),groups=inventory,
            scores={name:combine(gs,weights if name.startswith('delay') else np.ones(1)) for name,gs in arms.items()}))
        (HERE/f'results-{args.points}.json').write_text(json.dumps(dict(complete=len(results)==len(source['scans']),protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),elapsed_s=time.monotonic()-started,scans=results),indent=2)+'\n')
    print(json.dumps(results,indent=2))


if __name__=='__main__':main()
