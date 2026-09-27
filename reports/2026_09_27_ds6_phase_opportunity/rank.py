"""Training-only association ambiguity at the corrected pooled position."""
import importlib.util
import json
import time
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('envelope',ROOT/'2026_09_27_ds6_envelope_refit/run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def run():
    start=time.monotonic();parent=ROOT/'2026_09_27_ds6_envelope_refit/all-cfo_only.json';fit=json.loads(parent.read_text());assert fit['complete'] and fit['success'];p=json.loads((ROOT/'2026_09_27_ds6_fresh_joint43/protocol.json').read_text());x=fit['x'];rows=[]
    for si,sid in enumerate(p['splits']['all']):
        model,_,banks=m.fresh.load_model(sid,p['center']);point=np.array([x[0],x[1],x[si+2]]);exact=banks(np.array([point[2]]));predictions=model.evaluate(point,False,exact_banks=exact)['predictions'];lat,lon=model.coordinates(point);la,lo=np.radians([lat,lon]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]);rec=m.previous.phase.geo.geodetic_to_ecef_km(lat,lon,0);tracks=[]
        for t,pred in zip(model.tracks,predictions):
            if t['receiver_id']!=0:continue
            a,_,_=m.solver.scores(t['y'][None,:]-pred,t['mask']);pos=exact[t['track_id']][0][:,0];d=pos-rec;d/=np.linalg.norm(d,axis=-1,keepdims=True);visible=np.any((d@up)[:,t['mask']]>=0,axis=-1);a=np.where(visible,a,-np.inf);prob=np.exp(a-logsumexp(a));take=prob>0;entropy=float(-np.sum(prob[take]*np.log(prob[take])))
            tracks.append(dict(track_id=t['track_id'],entropy_nats=entropy,effective_candidates=float(np.exp(entropy)),map_mass=float(prob.max()),training_visits=int(t['mask'].sum()),held_visits=int((~t['mask']).sum())))
        rows.append(dict(session_id=sid,tracks=tracks));print('ranked',len(rows),round(time.monotonic()-start,1),flush=True)
    (HERE/'ranking.json').write_text(json.dumps(dict(complete=True,parent_sha256=m.fresh.digest(parent),scope='Frozen inherited shortlists; corrected training-only offsets; no phase or reference read',scans=rows,elapsed_s=time.monotonic()-start),indent=2)+'\n')


if __name__=='__main__':run()
