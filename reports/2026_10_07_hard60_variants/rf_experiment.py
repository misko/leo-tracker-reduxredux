"""Final-stage RF-offset experiment; control discovery/calibration remain frozen."""
from dataclasses import asdict
import time
import traceback
import numpy as np
import run_variants as run
from rf_model import RFObjective, Domain, fit_rf


def refine_rf_region(task):
    label,phase,xy,radius=task
    path=run.HERE/'results'/label/phase/'regions'/f'{xy[0]:g}_{xy[1]:g}_{radius:g}.json'
    source=run.control_folder(label)/'regions'/path.name
    original=run.read(source)
    out=dict(original,runs=[],candidates=[],reused_calibration_source=dict(path=str(source),sha256=run.data.digest(source)))
    if original['status']!='complete':
        out['unchanged_control_failure']=True
        run.engine.write(path,out)
        return out
    begun=time.monotonic()
    out['status']='running'
    try:
        _,obs,bank,prior,score=run.engine.context(label,phase)
        bank=bank.select(original['association']['selected_indices'])
        baseline=np.asarray(original['calibration']['receiver_baseline_hz'])
        native=RFObjective(run.engine.NativeObjective(obs,bank,prior,score,receiver_baseline_hz=baseline))
        oracle=RFObjective(run.engine.PositionObjective(obs,bank,prior,score,receiver_baseline_hz=baseline),
            gauge=(native.groups,native.group_basis,native.incidence))
        out.update(rf_groups=native.groups.tolist(),rf_group_basis=native.group_basis.tolist(),
                   rf_sigma_hz=50.,rf_limit_hz=150.,base_vector_size=native.base_size)
        penalty=original['calibration_penalty']
        post=np.asarray(original['calibration']['postfit']['vector'])
        def record(vector,arm,origin,**extra):
            v=native.augment(vector)
            value,gradient,terms=oracle.evaluate(v)
            fast,fg,_=native.evaluate(v)
            np.testing.assert_allclose(value,fast,atol=1e-6,rtol=0)
            np.testing.assert_allclose(gradient,fg,atol=1e-6,rtol=1e-7)
            audit=Domain(native,v,arm,xy,radius).audit(v,gradient)
            mass=float(terms.responsibilities.sum())
            rf_penalty=native.penalty(v)
            row=dict(arm=arm,origin=origin,vector=v.tolist(),objective=value,
                selection_score=value+penalty,data_nll=float(terms.nll),
                timing_penalty=value-terms.nll-rf_penalty,rf_penalty=rf_penalty,
                rf_offsets_hz=native.offsets(v).tolist(),
                frequency_rms_hz=float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)) if mass>1e-12 else None,
                signal_windows=mass,additional_slopes_hz_s=v[[3,5]].tolist(),
                calibration_slopes_hz_s=post[[3,5]].tolist(),
                combined_affine_slopes_hz_s=(v[[3,5]]+post[[3,5]]).tolist(),
                original_oracle_objective_delta=value-fast,**audit,**extra)
            out['candidates'].append(row)
            return row
        def fit_one(vector,arm,name,parent=None):
            v=native.augment(vector)
            if arm=='zero-c':v[6]=0.
            v=Domain(native,v,arm,xy,radius).start
            record(v,arm,'initial:'+name,parent_origin=parent)
            result=fit_rf(native,v,rf_arm=arm,local_center=xy,local_radius_km=radius)
            row=record(result.vector,arm,'fit:'+name,parent_origin=parent,
                elapsed_s=result.elapsed_s,stop_reason=result.stop_reason,evaluations=result.evaluations)
            np.testing.assert_allclose(row['objective'],result.objective,atol=1e-6,rtol=0)
            assert row['converged']==result.converged
            out['runs'].append(row)
            run.engine.write(path,out)
        for arm in ('zero-c','fitted-c'):
            for name in ('association','zero-timing'):
                v=np.asarray(original['association']['initial_vector']).copy()
                if name=='zero-timing':v[7:]=0.
                fit_one(v,arm,name)
            parent=min((r for r in out['candidates'] if r['arm']==arm and r['feasible']),key=lambda r:r['selection_score'])
            fit_one(parent['vector'],arm,'own-continuation',parent['origin'])
        out['status']='complete'
    except Exception as error:
        out.update(status='failed',error=str(error),traceback=traceback.format_exc())
    out['elapsed_s']=time.monotonic()-begun
    run.engine.write(path,out)
    print('RF REGION',label,xy,out['status'],out.get('error',''),flush=True)
    return out
