"""Matched full-cohort refits with phase factors for available source pairs."""
import argparse
import importlib.util
import json
import time
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
fresh=module('fresh',ROOT/'2026_09_27_ds6_fresh_joint43/run_joint43.py')
phase=module('continuous',ROOT/'2026_09_27_ds6_continuous_phase/run.py')


def run(name):
    started=time.monotonic();source=ROOT/'2026_09_27_ds6_fresh_joint43';p=json.loads((source/'protocol.json').read_text())
    assert fresh.digest(source/'run_joint43.py')==p['source_sha256']
    for path,digest in p['files'].items():assert fresh.digest(ROOT/path)==digest
    old=json.loads((source/f'{name}.json').read_text());assert old['complete'];sessions=old['sessions'];models=[]
    for sid in sessions:models.append(fresh.load_model(sid,p['center'])[0])
    pm=phase.Model();pm.banks=[b for b in pm.banks if b['scan']['session_id'] in sessions];indices=[sessions.index(b['scan']['session_id'])+2 for b in pm.banks]
    # Coordinates in the donor model use 111.195 km/degree; preserve identical
    # physical positions when passing them to the phase model's spherical map.
    conversion=(6371.0088*np.pi/180)/111.195
    def correction(x):
        y=np.r_[np.array(x[:2])*conversion,np.array(x)[indices]]
        return pm.evaluate(y,'phase')['train']-pm.evaluate(y,'cfo_only')['train']
    base=fresh.SparseJoint(models);initial=np.array(old['best']['x']);initial_train=-base.value_gradient(initial)[0]
    assert abs(initial_train-old['best']['train'])<1e-7
    protocol=dict(parent_sha256=fresh.digest(source/'protocol.json'),parent_fit_sha256=fresh.digest(source/f'{name}.json'),phase_protocol_sha256=phase.joint.sha(phase.HERE/'protocol.json'),sessions=sessions,phase_sessions=[b['scan']['session_id'] for b in pm.banks],initial=initial.tolist(),method='Matched warm-start refit; shared position and per-scan clocks; phase is joint-minus-CFO correction; maxiter40 maxfun80',scope='Conditional on existing CFO basin and frozen approximate candidate sets; phase only where extracted; no reference loaded')
    pp=HERE/f'{name}-protocol.json'
    with pp.open('x') as f:json.dump(protocol,f,indent=2)
    results={}
    for arm in ['cfo_only','phase']:
        def objective(x):
            value,gradient=base.value_gradient(x)
            if arm=='phase' and len(pm.banks):
                corr=correction(x);value-=corr
                for i in [0,1]+indices:
                    shifted=x.copy();step=-1e-4 if i>=2 and x[i]+1e-4>5 else 1e-4;shifted[i]+=step;gradient[i]-=(correction(shifted)-corr)/step
            return value,gradient
        fit=minimize(objective,initial.copy(),method='L-BFGS-B',jac=True,bounds=[(-12,12)]*2+[(-5,5)]*len(models),options=dict(maxiter=40,maxfun=80,ftol=1e-12,gtol=1e-5,maxls=30))
        held=sum(m.evaluate(np.array([fit.x[0],fit.x[1],fit.x[i+2]]),False)['held'] for i,m in enumerate(models));y=np.r_[fit.x[:2]*conversion,fit.x[indices]]
        if arm=='phase' and len(pm.banks):held+=pm.evaluate(y,'phase')['held']-pm.evaluate(y,'cfo_only')['held']
        results[arm]=dict(x=fit.x.tolist(),coordinates=models[0].coordinates(fit.x),train=-float(fit.fun),held=float(held),success=bool(fit.success),message=str(fit.message),nfev=int(fit.nfev),phase_correction=float(correction(fit.x)) if pm.banks else 0.)
        print(name,arm,results[arm],flush=True)
    (HERE/f'{name}.json').write_text(json.dumps(dict(complete=True,protocol_sha256=fresh.digest(pp),results=results,elapsed_s=time.monotonic()-started),indent=2)+'\n')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--fit',choices=['all','A','B'],required=True);run(ap.parse_args().fit)
