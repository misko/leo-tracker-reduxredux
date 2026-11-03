"""Conditional held prediction with source-shared candidate/revision states."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
sys.path.insert(0,str(HILL/'joint_orbit_uncertainty'))
from model import JointOrbit,direction,LOG_C,fast
spec=importlib.util.spec_from_file_location('joint_orbit_benchmark',HILL/'joint_orbit_uncertainty/run.py')
benchmark=importlib.util.module_from_spec(spec);spec.loader.exec_module(benchmark)


def predictive(model,x):
    rows=[]
    for unit_index,(members,count,size) in enumerate(model.units):
        training=np.zeros((count,len(model.beta)));joint=np.zeros_like(training);nheld=0
        for track,older in members:
            mask=track['mask'];nheld+=int((~mask).sum())
            base,visible=model.model.prediction(track,x)
            old=model.old_model.prediction(older,x)[0] if model.variant!='zero' else base
            delta,_=direction(old-base,np.zeros((*base.shape,3)),track['times_s'],mask,model.variant=='linear')
            residual=track['y'][None,None,:]-base[:,None,:]-model.beta[None,:,None]*delta[:,None,:]
            flat=residual[:,:,mask].reshape(-1,int(mask.sum()))
            offsets,audits=fast.fit_stationary_offsets(flat);assert all(a['converged'] for a in audits)
            offsets=offsets.reshape(count,-1)
            centered=residual-offsets[:,:,None]
            density=LOG_C-2.5*np.log1p((centered/100.)**2/4)
            prior=.5*(offsets/1e6)**2
            training+=np.where(visible[:,None],density[:,:,mask].sum(axis=2)-prior,-np.inf)
            joint+=np.where(visible[:,None],density.sum(axis=2)-prior,-np.inf)
        weights=np.log(model.weights)[None,:]
        train=float(logsumexp(training+weights)-np.log(size))
        complete=float(logsumexp(joint+weights)-np.log(size))
        rows.append(dict(unit_index=unit_index,tracks=len(members),candidates=count,held_rows=nheld,train=train,held=complete-train))
    return dict(training_score=sum(r['train'] for r in rows),held_score=sum(r['held'] for r in rows),units=rows)


def main():
    started=time.monotonic();rows=[];sources={}
    for index in (0,16):
        doc,older,config,mapping,scan,x,priors,bound=benchmark.context(index);sources.update(bound)
        audit_path=HILL/f'joint_orbit_uncertainty/{index:02d}.json';audit=benchmark.read(audit_path);assert audit['numerical_gate_pass']
        sources[str(audit_path)]=benchmark.digest(audit_path)
        arms={}
        for variant in ('zero','orbit','linear'):
            weights=priors['priors']['orbit' if variant=='zero' else variant]['weights']
            model=JointOrbit(doc,older,config,mapping,scan['groups'],scan['singletons'],variant,weights)
            arms[variant]=predictive(model,x)
            assert abs(arms[variant]['training_score']-audit['results'][variant]['score'])<1e-6
        rows.append(dict(index=index,arms=arms,orbit_vs_zero=arms['orbit']['held_score']-arms['zero']['held_score'],
                         orbit_vs_linear=arms['orbit']['held_score']-arms['linear']['held_score']))
    for p in (Path(__file__),HERE/'test_run.py',HERE/'PROTOCOL.md'):sources[str(p)]=benchmark.digest(p)
    result=dict(rows=rows,gate_pass=all(r['orbit_vs_zero']>0 and r['orbit_vs_linear']>0 for r in rows),sources=sources,
                position_fits=0,reference_used=False,elapsed_s=time.monotonic()-started)
    with (HERE/'outcome.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(gate_pass=result['gate_pass'],elapsed_s=result['elapsed_s'],scans=[{k:v for k,v in r.items() if k!='arms'} for r in rows]),indent=2))
if __name__=='__main__':main()
