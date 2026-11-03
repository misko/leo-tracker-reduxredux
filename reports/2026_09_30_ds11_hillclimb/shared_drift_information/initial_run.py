"""Conditional local position-information loss to shared linear drifts."""
import hashlib
import json
from pathlib import Path
import sys
import time
from collections import Counter
import numpy as np
from scipy.linalg import eigh

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
sys.path.insert(0,str(HERE.parents[2]/'tools'))
import ds7_fast_baseline_adapter as fast


def project(matrix,nuisance):
    if nuisance.shape[1]==0:return matrix.copy(),0
    u,s,_=np.linalg.svd(nuisance,full_matrices=False)
    rank=int(np.sum(s>s[0]*max(nuisance.shape)*np.finfo(float).eps)) if len(s) and s[0]>0 else 0
    q=u[:,:rank]
    return matrix-q@(q.T@matrix),rank


def retention(jac,nuisance):
    baseline,_=project(jac[:,:2],jac[:,2:3])
    changed,rank=project(jac[:,:2],np.column_stack((jac[:,2],nuisance)))
    f0=baseline.T@baseline;f1=changed.T@changed
    return dict(eigenvalues=eigh(f1,f0,eigvals_only=True).tolist(),
                nuisance_rank=rank,baseline_information=f0.tolist(),retained_information=f1.tolist())


def main():
    started=time.monotonic();source=HILL/'same_source_cfo_audit/results.json';identities=json.loads(source.read_text())
    # The prior source-bound full-candidate benchmark already binds the original
    # input plans, banks, identity audit and qualified endpoint products.
    binding=HILL/'cross_band_rx_fixed/outcome.json';bound=json.loads(binding.read_text());sources=dict(bound['sources'])
    for p,h in sources.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h
    assert str(source) in sources
    base=HILL.parent/'2026_09_30_ds11_single10';plan=json.loads((base/'plan.json').read_text())
    sidecar_path=HILL/'source_balance/catalogue_identities.json';sidecar=json.loads(sidecar_path.read_text())
    assert str(sidecar_path) in sources
    rows=[]
    for index in range(0,32,4):
        doc=fast.load_documents(dict(config=plan['config'],inputs=[plan['inputs'][index]]))[0]
        x=np.array(json.loads((base/f'runs/{index:02d}_iid.json').read_text())['selected']['x'])
        geometry=fast.Stationary(doc,plan['config'])
        idrows={r['track_id']:r for r in identities['track_rows'] if r['scan_index']==index}
        count=Counter(r['norad'] for r in idrows.values() if r['unambiguous'])
        numbers=sorted(n for n,c in count.items() if c>=2)
        receivers=sorted({int(t['receiver_id']) for t in doc['tracks']})
        jrows=[];zrows=[];rrows=[];covered=0
        for track in doc['tracks']:
            tid=track['track_id'];identity=idrows[tid];mask=track['mask']
            roster=sidecar['scans'][str(index)]['tracks'][tid]['candidate_norad']
            slot=roster.index(identity['norad'])
            jac=[]
            for axis,step in enumerate((1e-4,1e-4,1e-5)):
                d=np.eye(3)[axis]*step
                jac.append((geometry.prediction(track,x+d)[0][slot,mask]-geometry.prediction(track,x-d)[0][slot,mask])/(2*step))
            jac=np.array(jac).T;jac-=jac.mean(axis=0)
            t=np.array(track['times_s'])[mask];t-=t.mean()
            z=np.zeros((len(t),len(numbers)));r=np.zeros((len(t),len(receivers)))
            if identity['unambiguous'] and identity['norad'] in numbers:
                z[:,numbers.index(identity['norad'])]=t;covered+=1
            r[:,receivers.index(int(track['receiver_id']))]=t
            jrows.append(jac);zrows.append(z);rrows.append(r)
        jac=np.vstack(jrows)
        rows.append(dict(index=index,tracks=len(jrows),training_observations=len(jac),source_groups=len(numbers),source_covered_tracks=covered,
                         receiver_drift=retention(jac,np.vstack(rrows)),source_drift=retention(jac,np.vstack(zrows))))
    for p in (source,binding,sidecar_path,Path(__file__),HERE/'PROTOCOL.md',HERE/'test_run.py'):
        sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    summary={kind:dict(median_low_eigenvalue=float(np.median([r[kind]['eigenvalues'][0] for r in rows])),
                       median_high_eigenvalue=float(np.median([r[kind]['eigenvalues'][1] for r in rows]))) for kind in ('receiver_drift','source_drift')}
    output=dict(rows=rows,summary=summary,sources=sources,reference_used=False,position_fits=0,elapsed_s=time.monotonic()-started)
    with (HERE/'outcome.json').open('x') as f:json.dump(output,f,indent=2)
    print(json.dumps(dict(summary=summary,coverage=[{k:r[k] for k in ('index','tracks','source_groups','source_covered_tracks')} for r in rows],elapsed_s=output['elapsed_s']),indent=2))


if __name__=='__main__':main()

