"""Bounded matched existing native optimizer mechanism test; GPS absent."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import sys
from pathlib import Path
# Bind legacy input roots to the workspace while using the frozen numerical helpers.
sys.path.insert(0,'/home/mouse9911/gits/leo-tracker-reduxredux/tools')
import run_algo01_ds23_sample
ROOT=Path('/srv/bulk/leo/research/algo04-candidate-20261023/source')
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'upstream_tools'),'/srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/source']
import json, signal, time, hashlib
import numpy as np
from scipy.optimize import minimize
import experiment as exp
from ds23_feasible_position import feasible_fit
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_frequency_events import summary
from run_ds23_combined_recovery_full import valid

OUT=Path(__file__).resolve().parent
FROZEN=Path('/srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/raw')
def read(p): return json.loads(p.read_text())
def serial(o):
    if isinstance(o,np.ndarray):return o.tolist()
    if isinstance(o,np.generic):return o.item()
    raise TypeError(type(o).__name__)
def write(p,d):p.write_text(json.dumps(d,default=serial,indent=2)+'\n')
def qualifies(s):
    return bool(valid({'c0':s,'fitted_c':s}) and s['final_phase_change_s']<=.01)
def snapshot(p,x,entries):
    c=p.calculate(x); sl=gate_slacks(p,x,entries)
    return dict(endpoint_east_north_km=x,negative_twice_elbo=float(c['negative_twice_elbo']),
        gate_slacks=sl,minimum_gate_slack=min(sl.values()),
        failing_gates={k:v for k,v in sl.items() if v<0},
        conditional_RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),
        objective_terms={k:float(v) for k,v in c.items() if np.isscalar(v) and isinstance(v,(int,float,np.number))})
def setup(case):
    d,_=exp.context(case); frozen=read(FROZEN/case/'result.json');g=frozen['ordinary_graph']
    d=exp.apply_trial(d,g);kind=g['kind']
    selected=read(FROZEN/case/'native'/(case+'_persistent5s_selection.json'))['selected']
    scan,entries=exp.paths.native.append_native_paths(d['scan'],d['entries'],selected,exp.paths.native.receiver_basis(d['scan']))
    d=dict(d,scan=scan,entries=entries)
    primary=read(FROZEN/case/'native'/(case+'.json'))['methods']['persistent5s']
    return d,kind,primary,frozen,selected
def replay(d,kind,s):
    p=exp.paths.build(d,kind,s[0],s[1]['phase_reference']);x=np.asarray(s[1]['endpoint_east_north_km'])
    result=snapshot(p,x,d['entries']);result['saved_objective_difference']=result['negative_twice_elbo']-s[1]['negative_twice_elbo']
    if abs(result['saved_objective_difference'])>1e-5:raise ValueError('frozen objective failed replay')
    return result
def run(d,kind,arm,saved,method):
    reference=np.asarray(saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km']);history=[]
    started=time.monotonic()
    for epoch in range(5):
        p=exp.paths.build(d,kind,arm,reference);before=snapshot(p,x,d['entries']);trace=[]
        objective=lambda z:p.calculate(z)['negative_twice_elbo']
        # Record every distinct objective endpoint, including finite differences.
        seen=set()
        def recorded(z):
            key=tuple(z)
            if key not in seen:
                seen.add(key);trace.append(dict(x=np.asarray(z).copy(),objective=float(objective(z))))
            return objective(z)
        if method=='constrained':
            fitted=feasible_fit(recorded,lambda z:np.asarray(list(gate_slacks(p,z,d['entries']).values()))-.01,
                x,p.lower,p.upper,iterations=40)
        else:
            origin=float(objective(x))
            res=minimize(lambda z:recorded(z)-origin,x,method='SLSQP',bounds=list(zip(p.lower,p.upper)),
                options=dict(maxiter=40,ftol=1e-7,eps=1e-3))
            fitted=dict(parameters=res.x,score=float(res.fun+origin),solver_success=bool(res.success),
                solver_message=str(res.message),iterations=int(res.nit),evaluations=int(res.nfev))
        x=np.asarray(fitted['parameters']);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(epoch=epoch,before=before,after=snapshot(p,x,d['entries']),fit=fitted,
            phase_change_s=float(np.max(abs(phase-reference))),trace=trace))
        reference=phase
    result=summary(p,x,d['entries']);result['final_phase_change_s']=history[-1]['phase_change_s']
    result.update(snapshot(p,x,d['entries']))
    result['qualified']=qualifies(result)
    return dict(arm=arm,solver=method,seconds=time.monotonic()-started,start=saved['endpoint_east_north_km'],
        start_phase_reference=saved['phase_reference'],history=history,summary=result,
        interpretation='diagnostic_only' if not result['qualified'] else 'gate_qualified_RF_endpoint')
def main():
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180 second fit cap')))
    protocol=dict(cases=sys.argv[1:] or ['DS23-0365','DS23-0041','DS23-0272'],arms=['c0','fitted_c'],
        rounds=5,iterations_per_round=40,fit_seconds_cap=180,
        start='saved ordinary persistent5s endpoint and its phase reference, same within each solver pair',
        constraints='existing feasible_fit with original gate_slacks minus existing .01 rescue margin',
        controls='identical final native mask, aliases, priors, identities, bounds and phase refresh; no GPS in inference',
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    write(OUT/'protocol.json',protocol)
    for case in protocol['cases']:
        d,kind,primary,frozen,selected=setup(case)
        record=dict(case=case,kind=kind,selected_paths=selected,curved_mask=d['keep'],entries=d['entries'],
            node=d['node'],means=d['means'],original_protected=sorted(d['original_protected']),
            saved_native_accepted=primary['accepted'],saved_final_constrained_rescue=frozen['native_constrained_rescue'],
            replay={},fits=[])
        for label,arms in [('ordinary_native',primary['arms']),('published_final',frozen['final']['arms'])]:
            record['replay'][label]={a:replay(d,kind,(a,s)) for a,s in arms.items()}
        write(OUT/(case+'.json'),record)
        for arm in ['c0','fitted_c']:
            for method in ['ordinary','constrained']:
                signal.alarm(180)
                try:row=run(d,kind,arm,primary['arms'][arm],method)
                except TimeoutError as e:row=dict(arm=arm,solver=method,status='timeout',error=str(e))
                finally:signal.alarm(0)
                record['fits'].append(row);write(OUT/(case+'.json'),record)
                print(case,arm,method,row.get('summary',{}).get('minimum_gate_slack'),row.get('seconds'),flush=True)
    write(OUT/'results.json',dict(protocol=protocol,cases=[read(OUT/(c+'.json')) for c in protocol['cases']]))
if __name__=='__main__':main()
