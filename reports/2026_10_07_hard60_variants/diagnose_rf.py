"""Separate N64 diagnostic: truth-free continuation from existing final states.

These extra starts never enter the frozen three-variant benchmark.
"""
from dataclasses import asdict
import numpy as np
import run_variants as run
from rf_model import RFObjective,Domain,fit_rf


def main():
    label='N64'
    run.engine.CONTEXT[label]=run.data.load(label)
    _,obs,bank,prior,score=run.engine.context(label,'rf_offsets')
    folder=run.control_folder(label)
    control=run.read(folder/'result.json')
    xy=control['selections']['fitted-c']['result']['point']
    radius=control['selections']['fitted-c']['result']['local_radius_km']
    name=f'{xy[0]:g}_{xy[1]:g}_{radius:g}.json'
    original=run.read(folder/'regions'/name)
    tested=run.read(run.HERE/'results'/label/'rf_offsets'/'regions'/name)
    bank=bank.select(original['association']['selected_indices'])
    baseline=original['calibration']['receiver_baseline_hz']
    obj=RFObjective(run.engine.NativeObjective(obs,bank,prior,score,receiver_baseline_hz=baseline))
    oracle=RFObjective(run.engine.PositionObjective(obs,bank,prior,score,receiver_baseline_hz=baseline),
        gauge=(obj.groups,obj.group_basis,obj.incidence))
    starts={}
    for arm in ('zero-c','fitted-c'):
        starts['control:'+arm]=obj.augment(control['selections'][arm]['result']['vector'])
        pool=[c for c in tested['candidates'] if c['arm']==arm and c['feasible']]
        starts['rf-feasible:'+arm]=np.asarray(min(pool,key=lambda c:c['selection_score'])['vector'])
    rows=[]
    for arm in ('zero-c','fitted-c'):
        for name,start in starts.items():
            fit=fit_rf(obj,start,rf_arm=arm,local_center=xy,local_radius_km=radius)
            value,gradient,_=oracle.evaluate(fit.vector)
            np.testing.assert_allclose(value,fit.objective,atol=1e-6,rtol=0)
            check=Domain(obj,fit.vector,arm,xy,radius).audit(fit.vector,gradient)
            assert check['converged']==fit.converged
            row=dict(name=name,arm=arm,**asdict(fit),selection_score=value+original['calibration_penalty'],
                     rf_offsets_hz=obj.offsets(fit.vector),oracle_audit=check)
            rows.append(row)
            print('DIAGNOSTIC',arm,name,fit.converged,fit.stationarity,fit.objective,flush=True)
    run.engine.write(run.HERE/'rf_n64_diagnostic.json',dict(label=label,point=xy,radius=radius,
        scope=__doc__,rows=rows,sources={str(p):run.data.digest(p) for p in (run.HERE/'diagnose_rf.py',run.HERE/'rf_model.py')}))


if __name__=='__main__':main()
