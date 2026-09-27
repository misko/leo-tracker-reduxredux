"""Training-top-two offset stationarity audit at the pooled DS6 solution."""
import importlib.util
import json
import time
from pathlib import Path
import numpy as np
from scipy.special import gammaln
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
cohort=load('cohort',ROOT/'2026_09_27_ds6_cohort_phase/run.py');fresh=cohort.fresh
solver=load('stationary',ROOT/'2026_09_27_ds6_stationary_offsets/solver.py')
old=load('old',ROOT/'2026_09_27_ds6_exact_timing/robust.py')


def score(row,mask,offset):
    z=(row-offset)/100.;density=gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(100.)-2.5*np.log1p(z*z/4)
    return float(density[mask].sum()-.5*offset**2/1e12),float(density[~mask].sum())


def run():
    start=time.monotonic();path=ROOT/'2026_09_27_ds6_cohort_phase/all.json';fit=json.loads(path.read_text());assert fit['complete'];p=json.loads((ROOT/'2026_09_27_ds6_cohort_phase/all-protocol.json').read_text());parent=json.loads((ROOT/'2026_09_27_ds6_fresh_joint43/protocol.json').read_text());x=fit['results']['cfo_only']['x']
    protocol=dict(fit_sha256=fresh.digest(path),parent_protocol_sha256=fresh.digest(ROOT/'2026_09_27_ds6_fresh_joint43/protocol.json'),solver_sha256=fresh.digest(ROOT/'2026_09_27_ds6_stationary_offsets/solver.py'),sessions=p['sessions'],x=x,selection='Two highest original training-score visible candidates per track at pooled CFO winner; all43 scans; held data never choose candidates or modes',scope='Fixed-location diagnostic, not a refit or complete candidate-mode audit')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)
    rows=[]
    for si,sid in enumerate(p['sessions']):
        model,_,banks=fresh.load_model(sid,parent['center']);point=np.array([x[0],x[1],x[si+2]]);exact=banks(np.array([point[2]]));evaluated=model.evaluate(point,False,exact_banks=exact)
        lat,lon=model.coordinates(point);la,lo=np.radians([lat,lon]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]);rec=cohort.phase.geo.geodetic_to_ecef_km(lat,lon,0)
        tracks=[]
        for t,pred in zip(model.tracks,evaluated['predictions']):
            residual=t['y'][None,:]-pred;a,b=old.robust_scores(residual,t['mask']);pos=exact[t['track_id']][0][:,0];d=pos-rec;d/=np.linalg.norm(d,axis=-1,keepdims=True);visible=np.any((d@up)[:,t['mask']]>=0,axis=-1);selected=np.argsort(np.where(visible,a,-np.inf))[-min(2,int(visible.sum())):][::-1];candidates=[]
            assert len(selected)>0
            for i in selected:
                row=residual[i];before=float(old.fit_offset(row[t['mask']]));after,audit=solver.fit(row[t['mask']]);oldtrain,oldheld=score(row,t['mask'],before);newtrain,newheld=score(row,t['mask'],after);rr=before-row[t['mask']];gradient=float(np.sum(5*rr/(40000+rr*rr))+before/1e12)
                candidates.append(dict(candidate_index=int(exact[t['track_id']][2][i]),old_offset_hz=before,new_offset_hz=after,old_gradient_per_hz=gradient,old_train=oldtrain,new_train=newtrain,held_change=newheld-oldheld,**audit))
            tracks.append(dict(track_id=t['track_id'],candidates=candidates))
        rows.append(dict(session_id=sid,tracks=tracks));print(sid,'tracks',len(tracks),'elapsed',round(time.monotonic()-start,1),flush=True)
        (HERE/'results.json').write_text(json.dumps(dict(complete=len(rows)==43,protocol_sha256=fresh.digest(HERE/'protocol.json'),scans=rows,elapsed_s=time.monotonic()-start),indent=2)+'\n')


if __name__=='__main__':run()
