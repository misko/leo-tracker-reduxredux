"""Full-catalogue training mass at the two fitted positions; no reference read."""
import argparse
import json
import time
import numpy as np
from scipy.special import logsumexp
from run import Model,HERE,joint,geo


def run(arm):
    started=time.monotonic();model=Model();path=HERE/f'{arm}.json';fit=json.loads(path.read_text());assert fit['complete'];x=fit['best']['x'];lat,lon=model.coordinates(x);rec=geo.geodetic_to_ecef_km(lat,lon,0);la,lo=np.radians([lat,lon]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]);rows=[]
    for si,bank in enumerate(model.banks):
        for tid,b in bank['tracks'].items():
            total=kept=-np.inf;valid_count=0
            for first in range(0,len(bank['cat'].names),512):
                indices=np.arange(first,min(first+512,len(bank['cat'].names)));p,v,valid=geo.propagate_candidate_states(bank['cat'],indices,bank['start'],np.array(b['t']['times_s']),np.array([x[si+2]]));p=p[:,0];v=v[:,0];d=p-rec;d/=np.linalg.norm(d,axis=-1,keepdims=True);pred=-geo.REFERENCE_RF_HZ/geo.LIGHT_KM_S*np.sum(d*v,axis=-1);a,_=geo.pair.u.robust_scores(np.array(b['t']['measured_hz'])-pred,b['mask'],sigma=100.);visible=np.any((d@up)[:,b['mask']]>=0,axis=-1);a=np.where(visible,a,-np.inf);total=np.logaddexp(total,logsumexp(a));kept=np.logaddexp(kept,logsumexp(a[np.isin(valid,b['ids'])]));valid_count+=int(visible.sum())
            rows.append(dict(session_id=bank['scan']['session_id'],track_id=tid,retained_training_mass=float(np.exp(kept-total)),log_evidence_loss=float(total-kept),visible_candidates=valid_count))
        print(arm,bank['scan']['session_id'],'audited',len(rows),'elapsed',round(time.monotonic()-started,1),flush=True)
    (HERE/f'{arm}-coverage.json').write_text(json.dumps(dict(complete=True,fit_sha256=joint.sha(path),rows=rows,minimum_mass=min(r['retained_training_mass'] for r in rows),cfo_log_evidence_loss=sum(r['log_evidence_loss'] for r in rows),elapsed_s=time.monotonic()-started),indent=2)+'\n')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=['cfo_only','phase'],required=True);run(ap.parse_args().arm)
