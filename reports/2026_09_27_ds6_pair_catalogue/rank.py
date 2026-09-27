"""Rank eligible pairs by training-predicted nonlinearity, not held phase."""
import importlib.util
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('envelope',ROOT/'2026_09_27_ds6_envelope_refit/run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);geo=m.previous.phase.geo


def departure(geometry,times,first,last):
    fraction=(times-times[first])/(times[last]-times[first])
    return geometry-geometry[...,first,None]-(geometry[...,last]-geometry[...,first])[...,None]*fraction


def main():
    protocol=json.loads((HERE/'protocol.json').read_text());parent=json.loads((ROOT/'2026_09_27_ds6_fresh_joint43/protocol.json').read_text());fp=ROOT/'2026_09_27_ds6_envelope_refit/all-cfo_only.json';fit=json.loads(fp.read_text());hyp=json.loads((ROOT/'2026_09_27_ds6_joint_phase/protocol.json').read_text())['grid']['baselines'];vectors=np.array([b['enu_m'] for b in hyp]);rows=[]
    for record in protocol['selected']:
        sid=record['session_id'];path=HERE/f'{sid}-plan.json';plan=json.loads(path.read_text());assert plan['protocol_sha256']==m.fresh.digest(HERE/'protocol.json');groups=[]
        if plan['eligible_groups']:
            si=parent['splits']['all'].index(sid);x=np.array([fit['x'][0],fit['x'][1],fit['x'][si+2]]);model,_,banks=m.fresh.load_model(sid,parent['center']);exact=banks(np.array([x[2]]));predictions=model.evaluate(x,False,exact_banks=exact)['predictions'];lat,lon=model.coordinates(x);rec=geo.geodetic_to_ecef_km(lat,lon,0);la,lo=np.radians([lat,lon]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]);rotation=np.stack([[-np.sin(lo),np.cos(lo),0],[-np.sin(la)*np.cos(lo),-np.sin(la)*np.sin(lo),np.cos(la)],up],axis=-1)
            source=json.loads((ROOT/'2026_09_27_ds6_cfo_dataset'/f'{sid}-plan.json').read_text());archive=m.fresh.TleArchiveReader(Path('/var/lib/leo/tle'));_,cat,provenance=m.fresh.catalogues(archive,source['start_utc_ns'],source['snapshot_digest']);trackmodels={t['track_id']:(t,predictions[i]) for i,t in enumerate(model.tracks)}
            for group in plan['eligible_groups']:
                visits=sorted(group['visits'],key=lambda v:v['valid_start_counter']);train=np.array([v['partition']=='train' for v in visits]);ti=np.flatnonzero(train);times=np.array([(v['valid_start_counter']-plan['timing']['session_start_device_sample_counter'])/plan['rate_hz']+.056 for v in visits]);ids=[m['rx0_track_id'] for m in visits[0]['modes']];states=[];probabilities=[];entropy=0.
                for tid in ids:
                    t,pred=trackmodels[tid];a,_,_=m.solver.scores(t['y'][None,:]-pred,t['mask']);d=exact[tid][0][:,0]-rec;d/=np.linalg.norm(d,axis=-1,keepdims=True);a=np.where(np.any((d@up)[:,t['mask']]>=0,axis=-1),a,-np.inf);prob=np.exp(a-logsumexp(a));take=prob>0;entropy-=float(np.sum(prob[take]*np.log(prob[take])));probabilities.append(prob)
                    p,v,valid=geo.propagate_candidate_states(cat,exact[tid][2],source['start_utc_ns'],times,np.array([x[2]]));assert np.array_equal(valid,exact[tid][2]);d=p[:,0]-rec;d/=np.linalg.norm(d,axis=-1,keepdims=True);states.append(d@rotation)
                scale=2*np.pi*trackmodels[ids[0]][0]['rf_hz']/299792458.;geometry=scale*np.einsum('abtc,hc->abht',states[1][None,:,:,:]-states[0][:,None,:,:],vectors);curvature=departure(geometry,times,ti[0],ti[-1]);weight=probabilities[0][:,None,None,None]*probabilities[1][None,:,None,None]/len(vectors);rms=np.degrees(np.sqrt(np.sum(weight*curvature**2,axis=(0,1,2))));interior=ti[1:-1];best=int(interior[np.argmax(rms[interior])]) if len(interior) else None
                groups.append(dict(group=group['group'],track_ids=ids,training_visits=int(train.sum()),held_visits=int((~train).sum()),training_span_s=float(times[ti[-1]]-times[ti[0]]),entropy_nats=entropy,max_training_curvature_rms_deg=float(rms[best]) if best is not None else None,training_triplet=[visits[i]['visit'] for i in [ti[0],best,ti[-1]]] if best is not None else [],visit_ids=[v['visit'] for v in visits],predicted_departure_rms_deg=rms.tolist(),eligible_for_curvature=best is not None))
        rows.append(dict(session_id=sid,rate_msps=record['sample_rate_msps'],plan_sha256=m.fresh.digest(path),groups=groups));print(sid,len(groups),flush=True)
    candidates=[dict(session_id=s['session_id'],**g) for s in rows for g in s['groups'] if g['eligible_for_curvature']];ordered=sorted(candidates,key=lambda g:(-g['max_training_curvature_rms_deg'],g['session_id'],g['group']));selected=[];seen=set()
    for g in ordered:
        if g['session_id'] in seen:continue
        seen.add(g['session_id']);selected.append(g)
        if len(selected)==2:break
    out=dict(complete=True,protocol_sha256=m.fresh.digest(HERE/'protocol.json'),cfo_fit_sha256=m.fresh.digest(fp),scope='Training-CFO weighted RMS geometric departure from endpoint line; all 42 baseline hypotheses; no measured phase or reference; three train and two held required',scans=rows,ranked_pairs=ordered,selected=selected)
    (HERE/'ranking.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(selected,indent=2))


if __name__=='__main__':main()
