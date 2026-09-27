"""Does a pilot timing boundary outperform ordinary time partitions?"""
from pathlib import Path
import json,time
import numpy as np
from scipy.special import logsumexp
from cfo_scale_mixture import refine_bank
from segment_catalogue_trial import SCALES,mixture
import catalogue_trial as T

HERE=Path(__file__).resolve().parent
OUT=HERE/'boundary-controls'
SESSIONS=['scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3']

def stats(a):
    mean=a.mean(axis=-1)
    return a.shape[-1],mean,np.sum((a-mean[...,None])**2,axis=-1)

def scale_mixture(a,b,scales=SCALES):
    """Independent residual scales, one shared CFO offset; sufficient statistics."""
    n,ma,ssa=stats(a);m,mb,ssb=stats(b);result=np.full_like(ma,-np.inf)
    for sa in scales:
        for sb in scales:
            va,vb=float(sa)**2,float(sb)**2;wa,wb=n/va,m/vb;w=wa+wb;mean=(wa*ma+wb*mb)/w
            sse=ssa/va+ssb/vb+wa*(ma-mean)**2+wb*(mb-mean)**2
            ll=-.5*((n+m)*np.log(2*np.pi)+n*np.log(va)+m*np.log(vb)+np.log1p(1e12*w)+sse+mean**2/(1e12+1/w))
            result=np.logaddexp(result,ll)
    return result-2*np.log(len(scales))

def score(bank,tr_times,he_times,cut):
    tr=bank['train_residual'];he=bank['held_residual'];a=tr_times<cut;b=he_times<cut
    counts=[int(a.sum()),int((~a).sum()),int(b.sum()),int((~b).sum())]
    if min(counts)<3:return dict(eligible=False,counts=counts)
    train=scale_mixture(tr[...,a],tr[...,~a]);full=scale_mixture(np.concatenate([tr[...,a],he[...,b]],axis=-1),np.concatenate([tr[...,~a],he[...,~b]],axis=-1))
    ztr=float(logsumexp(train+bank['logprior']));zfull=float(logsumexp(full+bank['logprior']))
    return dict(eligible=True,counts=counts,log_train=ztr,log_full=zfull,held_predictive=zfull-ztr)

def model_mixture(train0,full0,alternatives):
    """Half prior on stationarity, half equally across proposed boundaries."""
    if not alternatives:return full0-train0
    tr=np.r_[train0,[r['log_train']-np.log(len(alternatives)) for r in alternatives]]
    full=np.r_[full0,[r['log_full']-np.log(len(alternatives)) for r in alternatives]]
    return float(logsumexp(full)-logsumexp(tr))

def main():
    OUT.mkdir(exist_ok=True);started=time.monotonic();model=json.loads((HERE/'timing-calibration.json').read_text())['model'];audit=json.loads((HERE/'phase-episodes/support-audit.json').read_text());results=[]
    protocol=dict(controls='Fixed acquisition-time quantiles .25,.375,.5,.625,.75; no CFO values or phase select control boundaries; minimum 3 train and 3 held blocks per side',models='One identity, orbit time and CFO intercept, independent residual scales across each tested boundary versus one shared scale',tau_step_s=.025,scales_hz=SCALES,selection='Fixed candidate bank for all boundaries within a track/fold; mode0 12:00 uses prior segment proposal union; other tracks use prior original banks. No new candidate search.',meaning='Retrospective negative controls, not unseen-scan validation or calibrated significance test')
    protocol['followup_model_mixture']='After reviewing boundary controls: half prior on stationary uncertainty, half equally across eligible proposed boundaries. Compare acquisition-triggered proposals against ordinary quantiles; weights from training evidence only. Exploratory follow-up, not a preregistered validation.'
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    for sid in SESSIONS:
        members=json.loads((HERE/'timing-trial'/f'{sid}-f1-q65-b161-membership.json').read_text())['tracks']
        for fold in (0,1):
            prior=json.loads((HERE/'timing-trial'/f'{sid}-f{fold}-q33.json').read_text());pt=np.array([r['time_s'] for r in prior['observations']]);T.FOLD=fold;T.PARTITION_OVERRIDES[sid]={int(b):bool(v) for b,v in zip(T.visit_bins(sid,pt),prior['phase_training_mask'])}
            for mode,m in enumerate(members):
                times=np.array(m['times_s']);mask=T.partition(sid,times);breaks=[r['time_s'] for t in audit['tracks'] if t['session_id']==sid and t['mode']==mode for r in t['supported_breaks']]
                special=sid==SESSIONS[1] and mode==0
                path=HERE/'segment-catalogue'/f'f{fold}-whole.npz' if special else HERE/'timing-trial'/f'{sid}-f{fold}-{m["track_id"][7:19]}.npz'
                bank=dict(np.load(path));bank['projection']=np.zeros((*bank['logprior'].shape,1));bank=refine_bank(bank,model,.025)
                ep=(times>=breaks[0]).astype(int) if special else np.zeros(len(times),int)
                block_times=[]
                for keep in (mask,~mask):
                    block_times.append(np.array([times[keep&(ep==e)&(np.floor(times)==b)].mean() for e in np.unique(ep) for b in np.unique(np.floor(times[keep&(ep==e)]))]))
                trt,het=block_times;assert len(trt)==bank['train_residual'].shape[-1] and len(het)==bank['held_residual'].shape[-1]
                train0=float(logsumexp(mixture(bank['train_residual'])+bank['logprior']));full0=float(logsumexp(mixture(np.concatenate([bank['train_residual'],bank['held_residual']],axis=-1))+bank['logprior']));base=full0-train0
                cuts=[('control',float(c)) for c in np.quantile(times,[.25,.375,.5,.625,.75])]+[('pilot_break',c) for c in breaks]
                trials=[]
                for kind,cut in cuts:
                    r=score(bank,trt,het,cut);r.update(kind=kind,cut_s=cut)
                    if r['eligible']:r['gain_nats']=r['held_predictive']-base
                    trials.append(r)
                controls=[r for r in trials if r['eligible'] and r['kind']=='control']
                # Predictive density of an equal-prior mixture over ordinary
                # boundaries: training evidence supplies weights, never held.
                control_mixture=float(logsumexp([r['log_full'] for r in controls])-logsumexp([r['log_train'] for r in controls])-base) if controls else None
                pilots=[r for r in trials if r['eligible'] and r['kind']=='pilot_break']
                rows=dict(session_id=sid,fold=fold,mode=mode,base_held_predictive=base,base_log_train=train0,base_log_full=full0,candidates=len(bank['candidate_ids']),trials=trials,control_mixture_gain_nats=control_mixture,generic_model_mixture_gain_nats=model_mixture(train0,full0,controls)-base,pilot_model_mixture_gain_nats=model_mixture(train0,full0,pilots)-base)
                results.append(rows);print(sid,fold,mode,'gains',[(r['kind'],round(r.get('gain_nats',0),3),r['eligible']) for r in trials],'mixture',control_mixture,flush=True)
                (OUT/'results.json').write_text(json.dumps(dict(protocol=protocol,results=results,elapsed_s=time.monotonic()-started),indent=2)+'\n')

if __name__=='__main__':main()
