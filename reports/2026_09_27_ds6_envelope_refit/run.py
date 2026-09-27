"""Corrected full-cohort likelihood using envelope finite differences."""
import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
previous=load('cohort',ROOT/'2026_09_27_ds6_cohort_phase/run.py');fresh=previous.fresh
solver=load('stationary_batch',ROOT/'2026_09_27_ds6_fast_offsets/solver.py')


def difference(function,point,index):
    step=1e-5
    if index>=2 and abs(point[index])>5-step:
        step=-step if point[index]>0 else step
        a=point.copy();b=point.copy();a[index]+=step;b[index]+=2*step
        return (-3*function(point)+4*function(a)-function(b))/(2*step)
    a=point.copy();b=point.copy();a[index]+=step;b[index]-=step
    return (function(a)-function(b))/(2*step)


class ProfileCache:
    def __init__(self):self.offsets=[];self.index=0;self.fixed=False
    def reset(self,fixed=False):
        self.index=0;self.fixed=fixed
        if not fixed:self.offsets=[]
    def score(self,residual,mask,sigma=100.):
        assert sigma==100.
        if self.fixed:offset=self.offsets[self.index]
        else:offset,_=solver.fit(residual[...,mask]);self.offsets.append(offset)
        self.index+=1;z=(residual-offset[...,None])/100.
        density=gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(100.)-2.5*np.log1p(z*z/4)
        tr=density[...,mask].sum(axis=-1)-.5*offset**2/1e12
        return tr,tr+density[...,~mask].sum(axis=-1)


class Objective:
    def __init__(self,models,pm,indices,arm):
        self.models=models;self.pm=pm;self.indices=indices;self.arm=arm;self.calls=0
    def correction(self,x,gradient=True):
        cache=ProfileCache();module=previous.phase.geo.pair.u;original=module.robust_scores;module.robust_scores=cache.score
        scale=(6371.0088*np.pi/180)/111.195
        def evaluate(point,fixed):
            y=np.r_[point[:2]*scale,point[self.indices]];cache.reset(fixed);a=self.pm.evaluate(y,'phase');cache.reset(True);b=self.pm.evaluate(y,'cfo_only');return a['train']-b['train'],a['held']-b['held']
        try:
            value,held=evaluate(x,False);g=np.zeros_like(x)
            if gradient:
                for i in [0,1]+self.indices:
                    g[i]=difference(lambda point:evaluate(point,True)[0],x,i)
            return value,g,held
        finally:module.robust_scores=original
    def value_gradient(self,x):
        total=0.;g=np.zeros_like(x);module=sys.modules[fresh.Objective.__module__];original=module.robust_scores
        try:
            for si,model in enumerate(self.models):
                cache=ProfileCache();module.robust_scores=cache.score;p=np.array([x[0],x[1],x[si+2]]);cache.reset();base=model.evaluate(p,False)['train'];total+=base
                for local,global_index in [(0,0),(1,1),(2,si+2)]:
                    def evaluate(point):
                        cache.reset(True);return model.evaluate(point,False)['train']
                    g[global_index]+=difference(evaluate,p,local)
        finally:module.robust_scores=original
        if self.arm=='phase' and self.pm.banks:
            v,d,_=self.correction(x);total+=v;g+=d
        self.calls+=1
        print(self.arm,self.calls,'train',total,flush=True)
        return -float(total),-g
    def held(self,x):
        module=sys.modules[fresh.Objective.__module__];original=module.robust_scores;held=0.
        try:
            for si,model in enumerate(self.models):
                cache=ProfileCache();module.robust_scores=cache.score;cache.reset();held+=model.evaluate(np.array([x[0],x[1],x[si+2]]),False)['held']
        finally:module.robust_scores=original
        if self.arm=='phase' and self.pm.banks:held+=self.correction(x,False)[2]
        return float(held)


def prepare(name):
    source=ROOT/'2026_09_27_ds6_fresh_joint43';p=json.loads((source/'protocol.json').read_text())
    assert fresh.digest(source/'run_joint43.py')==p['source_sha256']
    for path,digest in p['files'].items():assert fresh.digest(ROOT/path)==digest
    parent=ROOT/'2026_09_27_ds6_cohort_phase'/f'{name}.json';r=json.loads(parent.read_text());assert r['complete'];sessions=p['splits'][name]
    models=[fresh.load_model(sid,p['center'])[0] for sid in sessions];pm=previous.phase.Model();pm.banks=[b for b in pm.banks if b['scan']['session_id'] in sessions];indices=[sessions.index(b['scan']['session_id'])+2 for b in pm.banks]
    return models,pm,indices,np.array(r['results']['cfo_only']['x']),sessions,parent


def run(name,arm):
    start=time.monotonic();models,pm,indices,x,sessions,parent=prepare(name)
    protocol=dict(parent_sha256=fresh.digest(parent),solver_sha256=fresh.digest(ROOT/'2026_09_27_ds6_fast_offsets/solver.py'),sessions=sessions,phase_sessions=[b['scan']['session_id'] for b in pm.banks],initial=x.tolist(),method='Converged profiles at base; offsets fixed only for envelope derivatives; maxiter25 maxfun40 maxls12, train-only; same start for both arms',reference='Not loaded by fit',scope='Local matched full-cohort refit, frozen approximate candidate sets')
    pp=HERE/f'{name}-{arm}-protocol.json'
    with pp.open('x') as f:json.dump(protocol,f,indent=2)
    objective=Objective(models,pm,indices,arm);fit=minimize(objective.value_gradient,x,method='L-BFGS-B',jac=True,bounds=[(-12,12)]*2+[(-5,5)]*len(models),options=dict(maxiter=25,maxfun=40,maxls=12,ftol=1e-11,gtol=1e-5));held=objective.held(fit.x)
    out=dict(complete=True,protocol_sha256=fresh.digest(pp),arm=arm,fit=name,x=fit.x.tolist(),coordinates=models[0].coordinates(fit.x),train=-float(fit.fun),held=held,success=bool(fit.success),message=str(fit.message),nfev=int(fit.nfev),bound_hit=any(min(abs(v-a),abs(v-b))<.001 for v,(a,b) in zip(fit.x,[(-12,12)]*2+[(-5,5)]*len(models))),elapsed_s=time.monotonic()-start)
    (HERE/f'{name}-{arm}.json').write_text(json.dumps(out,indent=2)+'\n');print(out,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--fit',choices=['all','A','B'],required=True);ap.add_argument('--arm',choices=['cfo_only','phase'],required=True);args=ap.parse_args();run(args.fit,args.arm)
