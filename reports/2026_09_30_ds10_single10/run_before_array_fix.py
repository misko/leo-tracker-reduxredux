import hashlib,importlib.util,json,sys,time
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];REPORTS=HERE.parent
sys.path[:0]=[str(ROOT/'tools')]+[str(REPORTS/x) for x in ('2026_09_29_unassociated_trend','2026_09_29_frequency_contrast','2026_09_29_rx_cone_position','2026_09_29_correlated_contrast')]
import ds7_fast_baseline_adapter as baseline
from ds789_covariance_position import CovariancePosition
from contrast_position import ContrastPosition
from trend_mixture import TrendMixturePosition
from cone_position import ConePosition
from correlated_trend import CorrelatedTrendPosition

METHODS=['iid','shared','correlated','contrast','q020','q020_correlated','cone40','q020_cone40','slope','curvature']

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class IID:
    def __init__(self,docs,config):self.models=[baseline.Stationary(d,config) for d in docs]
    def evaluate(self,x,gradient=True,held=False):
        value,g=self.models[0].evaluate(x,gradient)
        return dict(score=value,gradient=g)

def main(index,method):
    started=time.monotonic();plan=json.loads((HERE/'plan.json').read_text());entry=plan['inputs'][index]
    for a in entry['artifacts']:assert 'sha256:'+hashlib.sha256(Path(a['path']).read_bytes()).hexdigest()==a['sha256']
    docs=baseline.load_documents(dict(config=plan['config'],inputs=[entry]));config=plan['config']
    base=TrendMixturePosition(docs,config,baseline.Stationary,.2)
    factories={'iid':lambda:IID(docs,config),'shared':lambda:CovariancePosition(docs,config,0,baseline.Stationary),
      'correlated':lambda:CovariancePosition(docs,config,10,baseline.Stationary),
      'contrast':lambda:ContrastPosition(docs,config,baseline.Stationary),'q020':lambda:base,
      'q020_correlated':lambda:CorrelatedTrendPosition(docs,config,baseline.Stationary),
      'cone40':lambda:ConePosition(docs,config,0,baseline.Stationary,40),
      'q020_cone40':lambda:CorrelatedTrendPosition(docs,config,baseline.Stationary,half_angle_deg=40,decay_s=0)}
    groups={};quadrature=None
    if method in ('slope','curvature'):
        prerequisite=json.loads((HERE/'runs'/f'{index:02d}_q020.json').read_text())
        selected=prerequisite['selected']
        if selected is None:raise ValueError('q020 prerequisite has no qualified fit')
        rows=base.evaluate(selected['x'],gradient=False,held=True)['rows']
        meta_path=next(Path(a['path']) for a in entry['artifacts'] if a['kind']=='candidates' and a['path'].endswith('.json'))
        bank_path=next(Path(a['path']) for a in entry['artifacts'] if a['kind']=='candidates' and a['path'].endswith('.npz'))
        meta={r['track_id']:r for r in json.loads(meta_path.read_text())['tracks']}
        with np.load(bank_path,allow_pickle=False) as bank:
            for ti,(track,row) in enumerate(zip(docs[0]['tracks'],rows)):
                slot=int(np.argmax(row['weights_given_signal']));times=track['times_s'][track['mask']]
                if row['signal_responsibility']*row['weights_given_signal'][slot]<.5:continue
                if method=='curvature' and (len(times)<8 or np.ptp(times)<10):continue
                identity=int(bank[f"candidate_ids_{meta[track['track_id']]['index']}"][slot])
                groups.setdefault((identity,float(track['rf_hz'])),[]).append((ti,slot))
        groups={k:v for k,v in groups.items() if len(v)>=2 and {docs[0]['tracks'][ti]['receiver_id'] for ti,slot in v}=={0,1}}
        membership={(0,ti):(key,slot) for key,v in groups.items() for ti,slot in v}
        folder='2026_09_29_shared_candidate_slope' if method=='slope' else '2026_09_29_shared_curvature'
        module=load_module('single_'+method,REPORTS/folder/'model.py')
        cls=module.SharedSlope if method=='slope' else module.SharedCurvature
        model=cls(docs,config,baseline.Stationary,membership,.5 if method=='slope' else .1)
    else:model=factories[method]()
    baseline.baseline.profile=baseline.profile
    starts=[]
    for east in (-2.,0.,2.):
        def objective(x):
            r=model.evaluate(x);return -r['score'],-r['gradient']
        fit=minimize(objective,[east,0.,0.],jac=True,method='L-BFGS-B',bounds=[(-12,12),(-12,12),(-5,5)],options=dict(maxiter=100,maxfun=160,ftol=1e-13,gtol=1e-6,maxls=25))
        boundary=any(min(v-lo,hi-v)<.001 for v,(lo,hi) in zip(fit.x,[(-12,12),(-12,12),(-5,5)]))
        audit=[]
        for axis,step in enumerate((1e-4,1e-4,1e-5)):
            delta=np.eye(3)[axis]*step
            numerical=(model.evaluate(fit.x+delta,gradient=False)['score']-model.evaluate(fit.x-delta,gradient=False)['score'])/(2*step)
            audit.append(abs(numerical+fit.jac[axis]))
        starts.append(dict(x=fit.x.tolist(),score=float(-fit.fun),success=bool(fit.success),message=str(fit.message),boundary=boundary,gradient=float(max(abs(fit.jac))),audit=max(audit),qualified=bool(fit.success and not boundary and max(abs(fit.jac))<=.01 and max(audit)<=.02)))
    valid=[s for s in starts if s['qualified']];selected=max(valid,key=lambda s:s['score']) if valid else None
    if selected:
        x=np.array(selected['x'])
        if method in ('slope','curvature'):
            a=model.evaluate(x,held=True);model.order=256;b=model.evaluate(x,held=True)
            quadrature=dict(score=abs(a['score']-b['score']),held=abs(a['held_score']-b['held_score']),gradient=float(max(abs(a['gradient']-b['gradient']))))
            if quadrature['score']>.02 or quadrature['held']>.02 or quadrature['gradient']>.01:selected=None
        if selected:
            common=base.evaluate(x,gradient=False,held=True)
            selected={**selected,'estimate_deg':list(base.models[0].coordinates(x)),
                      'common_q020_held':sum(r['held_log_score'] for r in common['rows'])}
    result=dict(index=index,method=method,session=entry['session_id'],starts=starts,selected=selected,quadrature=quadrature,groups=len(groups),elapsed_s=time.monotonic()-started)
    with (HERE/'runs'/f'{index:02d}_{method}.json').open('x') as f:json.dump(result,f,indent=2)

if __name__=='__main__':main(int(sys.argv[1]),sys.argv[2])
