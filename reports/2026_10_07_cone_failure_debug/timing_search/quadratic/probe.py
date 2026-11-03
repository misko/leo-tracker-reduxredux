"""Matched missing-RX-curvature causal probe; sigma1, no oracle/cross-arm seeds."""
import json,time,importlib.util
from pathlib import Path
from dataclasses import replace
import numpy as np
from quadratic_objective import QuadraticObjective

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parents[2]
SPEC=importlib.util.spec_from_file_location('quadratic_probe_loader',REPORTS/'2026_10_07_sigma1_root_cause/oracle.py')
loader=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(loader);controls=loader.CONTROLS

def run(case):
    from leo.analysis.regional_position_score import PositionObjective,coordinates
    from leo.analysis.regional_position_fit import fit_position
    from leo.contracts.regional_position import PositionScore
    target=HERE/(case+'.json')
    if target.exists():raise FileExistsError(target)
    begun=time.monotonic();doc,old,obs,prior,bank,checkpoint,prefix=loader.load(case)
    source=REPORTS/'2026_10_07_sigma1_cones'/case/'polished.json';receipt=json.loads(source.read_text())
    pool=[r for r in receipt['candidates'] if r['option']=='control' and r['feasible']]
    basin=min((r for r in pool if r['arm']=='fitted-c'),key=lambda r:r['selection_score'])['basin'];region=receipt['basins'][basin];center=np.array(region['center']);radius=region['radius_km']
    cal=checkpoint.get(prefix+':'+basin+':calibration')['result'];assoc=checkpoint.get(prefix+':'+basin+':association')['result'];subset=bank.select(assoc['selected_indices'])
    kwargs=dict(receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']));score=replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.)
    base=PositionObjective(obs,subset,prior,score,**kwargs);quad=QuadraticObjective(obs,subset,prior,score,**kwargs)
    seeds={a:min((r for r in pool if r['arm']==a and r['basin']==basin),key=lambda r:r['selection_score']) for a in controls.ARMS}
    calpen=seeds['fitted-c']['calibration_penalty'];minimum=max(-20.,subset.nodes_s[0]-obs.times_s.min());maximum=min(20.,subset.nodes_s[-1]-obs.times_s.max())
    audit=dict(parity=[],gradient_checks=[],gauge=[])
    for rx in (0,1):
        mask=obs.receiver==rx;t=obs.times_s-obs.time_center_s
        audit['gauge'].append(dict(rx=rx,sum=float(quad.quadratic[:,rx].sum()),linear_dot=float(quad.quadratic[:,rx]@t),peak_hz=float(np.max(abs(quad.quadratic[:,rx]))),other_rx_max=float(np.max(abs(quad.quadratic[~mask,rx])))))
    for arm in controls.ARMS:
        v=np.asarray(seeds[arm]['vector']);vp=np.r_[v,0.,0.]
        vb,gb,tb=base.evaluate(v);vq,gq,tq=quad.evaluate(vp)
        assert abs(vb-vq)<1e-8;np.testing.assert_allclose(gb,gq[:-2],atol=1e-9,rtol=0)
        assert abs(vb-seeds[arm]['objective'])<1e-6
        audit['parity'].append(dict(arm=arm,objective_discrepancy=abs(vb-vq),old_gradient_max_discrepancy=float(np.max(abs(gb-gq[:-2])))))
        probe=vp.copy();probe[-2:]=(.7,-.4);value,g,_=quad.evaluate(probe)
        for i in (0,6,7,len(vp)-2,len(vp)-1):
            step=1e-4 if i>=len(vp)-2 else 1e-5;d=np.eye(len(vp))[i]*step
            finite=(quad.evaluate(probe+d)[0]-quad.evaluate(probe-d)[0])/(2*step)
            error=abs(finite-g[i])/(1+abs(g[i]));assert error<.002
            audit['gradient_checks'].append(dict(arm=arm,coordinate=i,step=step,analytic=g[i],finite=finite,normalized_error=error))
    out=dict(case=case,session_id=old['session_id'],protocol_sha256=controls.digest_bytes(Path(__file__).read_bytes()),objective_sha256=controls.digest_bytes((HERE/'quadratic_objective.py').read_bytes()),source_receipt_sha256=controls.digest_bytes(source.read_bytes()),input_sha256=doc['input_manifest_sha256'],analysis_sha256=doc['analysis_manifest_sha256'],evidence_sha256=doc['evidence_sha256'],relative_sigma_s=1.,quadratic_coefficient_sigma=2.,design_peak_hz=100.,basin=basin,basin_selection='minimum original full-control fitted-c score',center=center,radius_km=radius,seconds_per_fit=20.,checks=audit,runs=[],selections=[],status='running')
    def save():target.with_suffix('.progress.json').write_text(json.dumps(out,default=controls.encode,indent=2))
    for option,o in (('control',base),('quadratic',quad)):
        for arm in controls.ARMS:
            original=np.asarray(seeds[arm]['vector']);seed=original.copy() if option=='control' else np.r_[original,0.,0.]
            fit=fit_position(o,seed,rf_arm=arm,maximum_seconds=20,maximum_iterations=600,local_center=center,local_radius_km=radius)
            value,g,t=o.evaluate(fit.vector);mass=float(t.responsibilities.sum());coeff=fit.vector[-2:] if option=='quadratic' else np.zeros(2)
            newpen=.5*np.sum((coeff/2)**2)
            result=dict(option=option,arm=arm,basin=basin,origin='fit',vector=fit.vector,objective=value,selection_score=value+calpen,data_nll=t.nll,timing_penalty=value-t.nll-newpen,quadratic_prior_penalty=newpen,quadratic_coefficients=coeff,quadratic_peak_amplitude_hz=coeff*100,posterior_rms_hz=float(np.sqrt(np.sum(t.responsibilities*t.residual_hz**2)/mass)),signal_fraction=mass/len(obs.window_ids),stop_reason=fit.stop_reason,elapsed_s=fit.elapsed_s,**controls.audit(fit.vector,g,o.basis,arm,prior.radius_km,center,radius,minimum,maximum))
            assert abs(result['stationarity']-fit.stationarity)<1e-5
            if option=='quadratic':
                h=1e-4;hessian=np.column_stack([(o.evaluate(fit.vector+np.eye(o.size)[i]*h)[1][-2:]-o.evaluate(fit.vector-np.eye(o.size)[i]*h)[1][-2:])/(2*h) for i in (o.size-2,o.size-1)])
                eig=np.linalg.eigvalsh((hessian+hessian.T)/2)
                result['conditional_quadratic_hessian']=hessian;result['conditional_quadratic_eigenvalues']=eig
                if eig.min()>0:result['conditional_quadratic_std_hz']=100*np.sqrt(np.diag(np.linalg.inv((hessian+hessian.T)/2)))
            out['runs'].append(dict(option=option,arm=arm,seed_sha256=controls.vector_digest(original),result=result));print(case,option,arm,round(result['selection_score'],3),result['converged'],result['quadratic_peak_amplitude_hz'],flush=True);save()
            candidates=[dict(r,origin='prior-incumbent',option=option,quadratic_peak_amplitude_hz=[0,0]) for r in pool if r['arm']==arm]
            if result['feasible']:candidates.append(result)
            out['selections'].append(min(candidates,key=lambda r:r['selection_score']))
    for r in [x['result'] for x in out['runs']]+out['selections']:
        lat,lon=np.radians(coordinates(prior,np.asarray(r['vector'])[:2]));a,b=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']]);h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
        r['horizontal_error_m']=float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
    out.update(status='complete',elapsed_s=time.monotonic()-begun);save();target.write_text(json.dumps(out,default=controls.encode,indent=2))

if __name__=='__main__':
    for case in ('1939','2139'):run(case)
