"""One bounded original-endpoint diagnostic; no optimization or reference ports."""
import importlib.util
import math
from pathlib import Path
import time

import numpy as np
from leo.analysis.regional_position_score import ALIAS_HZ

PARENT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


ENVELOPES = load('envelopes156_for158', PARENT/'2026_10_10_position_error_iter156/envelopes.py')
ADAPTIVE = load('adaptive157_for158', PARENT/'2026_10_10_position_error_iter157/adaptive.py')


def default_predict(model, vector):
    from leo.analysis.hard60_score import predict_orbits
    shifts = vector[7] + model.basis @ vector[8:]
    return predict_orbits(model.bank, model.observations, model.prior, vector[:2],
                          shifts, derivatives=False)[1]


def evidence(value):
    if isinstance(value, np.ndarray): return evidence(value.tolist())
    if isinstance(value, np.generic): return evidence(value.item())
    if isinstance(value, float) and not math.isfinite(value): return repr(value)
    if isinstance(value, dict): return {k:evidence(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)): return [evidence(v) for v in value]
    return value


def check(model, vector, coefficients, *, arm, stored_objective, stored_joint_objective,
          conditional_factory, feasible, anchor_audit, fingerprint, begun=None,
          clock=time.monotonic, visibility_factory=default_predict):
    begun = clock() if begun is None else begun
    row = dict(status='failed', axes={str(r):dict(status='unattempted') for r in (0,1)},
               calls=[], joint_attempts=0, visibility_calls=0, anchor=None, live_anchor_audit=None,
               normalized_marginal_bounds=None, elapsed_s=None)
    axis = None; expected_clock = None; expired = False; anchor_gradients = None
    try:
        original_v, original_c = np.array(vector,float,copy=True), np.array(coefficients,float,copy=True)
        if arm not in ('zero-c','fitted-c') or not math.isfinite(begun):
            raise ValueError('invalid arm/deadline origin')
        if not all(math.isfinite(x) for x in (stored_objective,stored_joint_objective)):
            raise ValueError('nonfinite saved objective')
        sigma, clutter, detection = model.score.sigma_hz, model.score.clutter_rate, model.score.detection_budget
        count = len(model.bank.numbers)
        if (not all(math.isfinite(x) for x in (sigma,clutter,detection))
                or not 0 < sigma <= 1000 or clutter <= 0 or not 0 < detection < count):
            raise ValueError('unsupported nearest-image/clutter/detection policy')
        identity = evidence(fingerprint()); row['inference_fingerprint'] = identity
        def unchanged():
            if evidence(fingerprint()) != identity: raise ValueError('inference arrays mutated')
        def deadline():
            nonlocal expired
            if clock()-begun >= 30:
                expired=True; raise TimeoutError('30-second soft endpoint budget exhausted')
        def physical(v,c):
            deadline()
            if not np.array_equal(v,original_v) or not np.isfinite(v).all() or not np.isfinite(c).all():
                raise ValueError('fixed physical state changed or nonfinite')
            if arm=='zero-c' and (v[6]!=0 or np.any(c[-2:]!=0)):raise ValueError('zero-c locks violated')
            result=feasible(v.copy(),c.copy())
            if not bool(result.get('feasible') if isinstance(result,dict) else result):raise ValueError('physical feasibility rejected')
            unchanged()
        physical(original_v,original_c)
        start=clock();deadline();row['visibility_calls']+=1
        try:
            visible=np.asarray(visibility_factory(model,original_v.copy()))
        finally:row['visibility_elapsed_s']=clock()-start
        unchanged();deadline()
        receivers=np.asarray(model.observations.receiver)
        if visible.shape!=(len(receivers),count) or visible.dtype!=bool:raise ValueError('invalid visibility mask')
        q=detection/count; b=clutter/ALIAS_HZ
        rho=visible.sum(axis=1)*q/((1-q)*sigma*np.sqrt(2*np.pi)*b)
        if not np.isfinite(rho).all():raise ValueError('nonfinite peak/clutter bound')
        row['bound_inputs']=dict(sigma_hz=sigma,alias_hz=ALIAS_HZ,clutter_density=b,
                                detection_probability=q,visible_counts=visible.sum(axis=1),rho=rho)
        expected_clock=original_c.copy()
        class GuardedModel:
            def __getattr__(self,name):return getattr(model,name)
            def evaluate_joint(self,v,c):
                nonlocal anchor_gradients
                if row['joint_attempts']>=1025:raise ValueError('global joint-attempt cap')
                event=dict(axis=axis,called=False,elapsed_s=None,objective_elapsed_s=None)
                row['calls'].append(event);row['joint_attempts']+=1;start=clock()
                try:
                    deadline()
                    if not np.array_equal(c,expected_clock):raise ValueError('conditional clock delta differs')
                    physical(v,c);deadline();event['called']=True;actual=clock()
                    try:value,pg,cg,terms=model.evaluate_joint(v.copy(),c.copy())
                    finally:event['objective_elapsed_s']=clock()-actual
                    unchanged()
                    pg,cg=np.asarray(pg),np.asarray(cg)
                    if (not np.isfinite(value) or pg.shape!=original_v.shape or cg.shape!=original_c.shape
                            or not np.isfinite(pg).all() or not np.isfinite(cg).all()):raise ValueError('invalid callback result')
                    if axis is None:anchor_gradients=(pg.copy(),cg.copy())
                    return value,pg.copy(),cg.copy(),terms
                except Exception as error:
                    event['error']=repr(error)
                    raise
                finally:event['elapsed_s']=clock()-start
        modes=conditional_factory(GuardedModel(),original_v.copy(),original_c.copy(),arm=arm)
        if row['joint_attempts']!=1 or anchor_gradients is None:raise ValueError('one anchor call required')
        row['anchor']=dict(value=modes.anchor_value,stored_objective=stored_objective,
                           stored_joint_objective=stored_joint_objective)
        if abs(modes.anchor_value-stored_objective)>1e-6 or abs(modes.anchor_value-stored_joint_objective)>1e-6:
            raise ValueError('anchor objective mismatch')
        deadline()
        audit=anchor_audit(original_v.copy(),original_c.copy(),*anchor_gradients,arm)
        row['live_anchor_audit']=evidence(audit)
        if not audit.get('qualified'):raise ValueError('anchor qualification failed')
        for r in (0,1):
            axis=r;deadline();start=clock()
            selected=receivers==r
            directions=np.asarray(model.clock_design)[selected,modes.slices[r]]@modes.direction
            h,u=ENVELOPES.curvature_bounds(directions,rho[selected],sigma,modes.precision)
            callback_count=0
            def callback(a):
                nonlocal expected_clock,callback_count
                if callback_count>=512:raise ValueError('receiver call cap')
                callback_count+=1
                expected_clock=original_c.copy()
                expected_clock[modes.slices[r]]+=modes.direction*(a-modes.amplitudes[r])
                result=modes.scalar(r,a)
                return -result['difference'],-result['gradient']
            def seams(left,right):
                deadline()
                return ENVELOPES.seam_log_bound(directions,rho[selected],sigma,ALIAS_HZ,(right-left)/2)
            result=ADAPTIVE.integrate(callback,*modes.intervals[r],h_bound=h,u_bound=u,
                                     seam_bound=seams,target_log_width=5e-5,maximum_calls=512)
            row['axes'][str(r)]=dict(status='deadline_exhausted' if expired else result['status'],
                h_bound=h,u_bound=u,interval=modes.intervals[r],elapsed_s=clock()-start,
                scalar_callback_attempts=callback_count,integration=result)
            if expired:break
            if result['status'] not in ('target_met','budget_exhausted','partition_resolution_exhausted'):
                raise ValueError('scalar integration failed; retained ledger is authoritative')
        unchanged()
        axes=[row['axes'][str(r)] for r in (0,1)]
        if all(a['status']=='target_met' for a in axes):
            bounds=[a['integration']['bounds'] for a in axes]
            normalizer=math.log(modes.precision/(2*math.pi))
            lower=modes.anchor_value-sum(v['log_upper'] for v in bounds)-normalizer
            upper=modes.anchor_value-sum(v['log_lower'] for v in bounds)-normalizer
            row['normalized_marginal_bounds']=dict(lower=lower,upper=upper,width=sum(v['log_width'] for v in bounds))
            row['status']='passed' if row['normalized_marginal_bounds']['width']<=1e-4 else 'unresolved'
        else:row['status']='unresolved'
    except Exception as error:
        row['error']=repr(error)
        row['status']='unresolved' if expired else 'failed'
    finally:
        row['actual_joint_calls']=sum(c['called'] for c in row['calls'])
        row['elapsed_s']=clock()-begun
        row['scope']='Conservative numerical envelope only; no rigorous certification or positioning claim'
    return evidence(row)
