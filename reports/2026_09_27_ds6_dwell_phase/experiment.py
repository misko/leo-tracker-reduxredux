"""Conditional whole-window validation of pooled two-source dwell phase."""
import sys,json,hashlib,time,copy
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares

HERE=Path(__file__).resolve().parent
PREV=HERE.parent/'2026_09_27_latest_ten_phase'
sys.path.insert(0,str(PREV))
import phase
SEED=2026092708

def refine_window(iq,visit,rate,start,result):
    """Refine common differential CFO using fitting samples only, then refit IQ."""
    correction=float(np.mean([m['frequency_hz'] for m in result['modes']]))
    adjusted=copy.deepcopy(visit)
    for mode in adjusted['modes']:mode['seeds'][1]['cfo_hz']+=correction
    refined=phase.analyze(iq,adjusted,rate,start)
    refined['initial_both_qualified']=result['both_qualified']
    refined['common_cfo_refinement_hz']=correction
    refined['both_qualified']=refined['both_qualified'] and result['both_qualified']
    return adjusted,refined

def frames(iq,visit,rate,start,result):
    designs,_=phase.designs_for(visit,rate,start,len(iq),result['timing_offsets_samples'],False)
    masks,_=phase.masks(len(iq),rate)
    out={}
    for label,mask in [('fit',masks[0]),('evaluation',masks[2])]:
        co=[np.linalg.lstsq(np.column_stack(designs[rx])[mask],iq[mask,rx],rcond=None)[0] for rx in (0,1)]
        z=co[1]*np.conj(co[0]);power=abs(np.column_stack(designs[0]))**2
        t=(power[mask]*(np.arange(len(iq))[mask]/rate)[:,None]).sum(axis=0)/power[mask].sum(axis=0)
        mode=np.concatenate([np.full(d.shape[1],i) for i,d in enumerate(designs[0])])
        out[label]=dict(t=t-len(iq)/(2*rate),z=z/np.maximum(abs(z),1e-30),s=2*mode-1)
    return dict(midpoint=(start+len(iq)/2)/rate,data=out,result=result)

def residual(pred,z):
    d=np.exp(1j*pred)-z
    return np.r_[d.real,d.imag]

def fit_joint(windows,indices,rate_bound):
    ref=np.mean([w['midpoint'] for w in windows]);best=None
    for slope in np.linspace(-rate_bound,rate_bound,5):
        dd=np.angle(np.mean([np.exp(1j*(w['result']['modes'][1]['train']['phase_rad']-w['result']['modes'][0]['train']['phase_rad']-2*np.pi*slope*(w['midpoint']-ref))) for w in [windows[i] for i in indices]]))
        initial=[]
        for i in indices:
            w=windows[i];initial.extend([w['result']['modes'][0]['train']['phase_rad']+(dd+2*np.pi*slope*(w['midpoint']-ref))/2,np.mean([m['frequency_hz'] for m in w['result']['modes']])])
        initial.extend([dd,slope*.999])
        def fun(p):
            errors=[]
            for j,i in enumerate(indices):
                w=windows[i];d=w['data']['fit'];a,f=p[2*j:2*j+2]
                pred=a+2*np.pi*f*d['t']+d['s']/2*(p[-2]+2*np.pi*p[-1]*(w['midpoint']+d['t']-ref))
                errors.extend(residual(pred,d['z']))
            return errors
        lo=np.full(len(initial),-np.inf);hi=-lo;lo[-1]=-rate_bound;hi[-1]=rate_bound
        fit=least_squares(fun,initial,bounds=(lo,hi),max_nfev=200)
        if best is None or fit.cost<best.cost:best=fit
    return dict(dd=float(best.x[-2]),rate=float(best.x[-1]),ref=float(ref),cost=float(best.cost))

def evaluate(windows,train,held,bound):
    model=fit_joint(windows,train,bound);errors=[];base=[]
    for i in held:
        w=windows[i];d=w['data']['fit'];m=w['result']['modes']
        predict=lambda p,d:p[0]+2*np.pi*p[1]*d['t']+d['s']/2*(model['dd']+2*np.pi*model['rate']*(w['midpoint']+d['t']-model['ref']))
        init=[m[0]['train']['phase_rad']+(model['dd']+2*np.pi*model['rate']*(w['midpoint']-model['ref']))/2,np.mean([x['frequency_hz'] for x in m])]
        fit=least_squares(lambda p:residual(predict(p,d),d['z']),init,max_nfev=200)
        d=w['data']['evaluation'];errors.extend(phase.wrap(np.angle(d['z'])-predict(fit.x,d)))
        pred=np.array([m[int((s+1)/2)]['train']['phase_rad']+2*np.pi*m[int((s+1)/2)]['frequency_hz']*t for s,t in zip(d['s'],d['t'])])
        base.extend(phase.wrap(np.angle(d['z'])-pred))
    rms=lambda v:float(np.degrees(np.sqrt(np.mean(np.square(v)))))
    return dict(model=model,held_frame_count=len(errors),held_rms_deg=rms(errors),baseline_held_rms_deg=rms(base))

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--refine',action='store_true');args=parser.parse_args()
    output=HERE/'refined' if args.refine else HERE;output.mkdir(exist_ok=True)
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    plan=json.loads((PREV/'plan.json').read_text());ds6=json.loads((HERE.parent/'2026_09_27_ds6_roof/manifest.json').read_text());members={r['session_id']:r for r in ds6['captures']}
    chosen=[]
    for scan in plan['scans']:
        paired=[v for v in scan['selected'] if len(v['modes'])==2]
        if paired:
            v=sorted(paired,key=lambda v:hashlib.sha256(f"{SEED}:{scan['session_id']}:{v['visit']}".encode()).hexdigest())[0]
            chosen.append((scan,v))
    protocol=dict(seed=SEED,selection='One metadata-selected paired dwell per cached scan; hash ordering; no phase-result selection',scans=[dict(session_id=s['session_id'],visit=v) for s,v in chosen],arms_hz=[.2,20.],validation='Three random whole windows fit DD; remaining qualified windows evaluate. Held-window fit samples estimate only common receiver intercept/rate. Evaluation samples estimate no nuisance parameters.')
    protocol['common_cfo_refinement']=args.refine
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True);results=[];started=time.monotonic()
    for scan,v in chosen:
        sid=scan['session_id'];cap=store.inspect(sid);assert cap.manifest_sha256==scan['capture_digest']==members[sid]['manifest_sha256']
        with store.reader(sid,expected=cap) as reader:_,raw=reader.read_visit_ci16(v['visit'])
        iq=raw[...,0].astype(float)+1j*raw[...,1].astype(float);rate=scan['rate_hz'];windows=[]
        for ms in plan['starts_ms']:
            start=round(ms*rate/1000);n=round(plan['width_ms']*rate/1000)
            r=phase.analyze(iq[start:start+n],v,rate,start)
            adjusted=v
            if args.refine:adjusted,r=refine_window(iq[start:start+n],v,rate,start,r)
            windows.append(frames(iq[start:start+n],adjusted,rate,start,r))
        order=np.random.default_rng(SEED+v['visit']).permutation(len(windows));train=[int(i) for i in order[:3] if windows[i]['result']['both_qualified']];held=[int(i) for i in order[3:] if windows[i]['result']['both_qualified']]
        row=dict(session_id=sid,visit=v['visit'],train_windows=train,held_windows=held,qualified_windows=sum(w['result']['both_qualified'] for w in windows),arms=[])
        if len(train)>=2 and held:
            row['arms']=[dict(rate_bound_hz=b,**evaluate(windows,train,held,b)) for b in [.2,20.]]
        else:row['unavailable_reason']='Fewer than two qualified training windows or no qualified held window'
        results.append(row)
        def serial(x):
            if isinstance(x,np.ndarray):return dict(real=x.real.tolist(),imag=x.imag.tolist()) if np.iscomplexobj(x) else x.tolist()
            raise TypeError(type(x))
        (output/f'{sid}-frames.json').write_text(json.dumps(windows,default=serial)+'\n')
        (output/'results.json').write_text(json.dumps(dict(results=results,elapsed_s=time.monotonic()-started),indent=2)+'\n')
        print(json.dumps(row),flush=True)
    store.close()
if __name__=='__main__':main()
