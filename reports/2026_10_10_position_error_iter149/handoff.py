"""Explicit fixed-position discovery-to-fitted calibration transition."""
import copy
import types

def promote(model,fit,point,discovery_arm,*,audit,qualify):
    """Audits are mandatory even when the saved arm's converged flag is true."""
    original = copy.deepcopy(fit)
    if discovery_arm not in ('fitted-c','zero-c'):raise ValueError('unknown discovery arm')
    if fit['vector'][:2]!=list(point):raise ValueError('fixed point changed')
    if discovery_arm=='zero-c' and fit['vector'][6]!=0:raise ValueError('zero c lock changed')
    own = audit(model, fit, discovery_arm)
    free = audit(model, fit, 'fitted-c')
    receipt=dict(discovery_arm=discovery_arm,original=original,discovery_audit=own,fitted_audit=free,repair=None,promoted=None,status='discovery-unqualified')
    if not own['qualified']:return receipt
    candidate=copy.deepcopy(fit)
    if not free['qualified']:
        repaired=qualify(model,fit['vector'],fit['objective'],retained=True,stage='calibration-prefit',independently_qualified=False,maximum_rounds=2,maximum_evaluations=100)
        receipt['repair']=repaired
        if not repaired['qualified']:return dict(receipt,status='promotion-unqualified')
        candidate=copy.deepcopy(repaired['fit'])
    if list(candidate['vector'][:2])!=list(point):raise ValueError('repair moved fixed point')
    final=audit(model,candidate,'fitted-c')
    receipt['promoted_audit']=final
    if not final['qualified']:return dict(receipt,status='promotion-unqualified')
    candidate['converged']=True
    return dict(receipt,status='qualified',promoted=candidate)

def recovery_port(backend,discovery_arm):
    """Clone105 function environment; never mutate loaded module globals."""
    original = backend['recovered_region']
    environment = dict(original.__globals__)
    direct = environment['direct']
    np = environment['np']
    core = environment['core']
    def audit(model,fit,arm):
        vector=np.asarray(fit['vector'],float)
        value,gradient,_=model.evaluate(vector)
        if not np.isfinite(value) or not np.isfinite(gradient).all():raise ValueError('nonfinite coarse model')
        if abs(value-fit['objective'])>1e-6:raise ValueError('coarse objective changed')
        problem=direct.continuation._Problem(model,vector,fixed_position=True,rf_arm=arm,slope_half_width_hz_s=60)
        stationarity=float(problem.stationarity(vector,gradient));feasible=bool(problem.feasible(vector))
        return dict(objective=float(value),stationarity=stationarity,feasible=feasible,qualified=feasible and stationarity<=.001,rf_arm=arm)
    def calibration(observations,bank,prior,trigger):
        model,fit=environment['verify_coarse'](observations,bank,prior,trigger['original'])
        point=[float(x) for x in trigger['key'].split(':')[1:]]
        transition=promote(model,fit,point,discovery_arm,audit=audit,qualify=direct.qualification.qualify)
        transition['legacy_gate_rejected_original']=not (bool(fit['converged']) and transition['fitted_audit']['qualified'])
        if transition['promoted'] is None:return dict(status=transition['status'],calibration=None,handoff=transition)
        promoted=transition['promoted']
        try:
            prefit=direct.validated_postfit(model,promoted,np.asarray(point))
            after=direct.fresh_calibration(observations,model,prior,trigger['original']['bootstrap']['satellite_indices'],prefit)
        except (ValueError, AssertionError) as error:
            return dict(status='promoted-calibration-failed',calibration=None,handoff=transition,error=repr(error))
        return dict(after,handoff=transition,direct_prefit=core.json_value(prefit))
    environment['recover_calibration']=calibration
    return types.FunctionType(original.__code__,environment,original.__name__,original.__defaults__,original.__closure__)
