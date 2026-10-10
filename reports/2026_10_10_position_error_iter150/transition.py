"""Original-state bounded nonlinear promotion before unchanged Newton polish."""
import copy
import time
import types

def transition(model, original, point, arm, *, audit, bounded, qualify):
    original = copy.deepcopy(original)
    if list(original['vector'][:2]) != list(point):
        raise ValueError('fixed point changed')
    if arm not in ('zero-c', 'fitted-c'):
        raise ValueError('unknown discovery arm')
    if arm == 'zero-c' and original['vector'][6] != 0:
        raise ValueError('original zero lock violated')
    own = audit(model, original, arm)
    free = audit(model, original, 'fitted-c')
    receipt = dict(original=original, discovery_arm=arm, discovery_audit=own,
                   fitted_audit=free, nonlinear=None, polish=None, promoted=None,
                   status='discovery-unqualified', legacy_gate_rejected_original=not (original['converged'] and free['qualified']))
    if not own['qualified']:
        return receipt
    candidate = copy.deepcopy(original)
    if not free['qualified']:
        begun = time.monotonic()
        try:
            candidate, solver = bounded(model, copy.deepcopy(original['vector']), rf_arm='fitted-c',
                                        fixed_position=True, slope_half_width_hz_s=60,
                                        maximum_seconds=5, maximum_iterations=200)
            candidate = copy.deepcopy(candidate)
            receipt['nonlinear'] = dict(fit=candidate, solver=solver,
                                        elapsed_s=time.monotonic()-begun)
            if candidate is None:
                raise ValueError('bounded promotion returned no feasible state')
            if list(candidate['vector'][:2]) != list(point):
                raise ValueError('nonlinear promotion moved point')
            check = audit(model, candidate, 'fitted-c')
            receipt['nonlinear'].update(audit=check, elapsed_s=time.monotonic()-begun)
        except (ValueError, TimeoutError, AssertionError) as error:
            details = receipt['nonlinear'] or {}
            details.update(error=repr(error), elapsed_s=time.monotonic()-begun)
            return dict(receipt, status='nonlinear-promotion-failed', nonlinear=details)
        if not check['feasible'] or candidate['objective'] > original['objective'] + 1e-6:
            return dict(receipt, status='nonlinear-promotion-invalid')
        if not check['qualified']:
            repair = qualify(model, candidate['vector'], candidate['objective'], retained=True,
                             stage='calibration-prefit', independently_qualified=False,
                             maximum_rounds=2, maximum_evaluations=100)
            receipt['polish'] = repair
            if not repair['qualified']:
                return dict(receipt, status='promotion-unqualified')
            candidate = copy.deepcopy(repair['fit'])
    if list(candidate['vector'][:2]) != list(point):
        raise ValueError('polish moved point')
    final = audit(model, candidate, 'fitted-c')
    receipt['promoted_audit'] = final
    if not final['qualified']:
        return dict(receipt, status='promotion-unqualified')
    candidate['converged'] = True
    return dict(receipt, status='qualified', promoted=candidate)

def recovery_port(backend, arm):
    original = backend['recovered_region']
    environment = dict(original.__globals__)
    direct, np, core = environment['direct'], environment['np'], environment['core']
    def audit(model, fit, rf_arm):
        vector = np.asarray(fit['vector'], float)
        value, gradient, _ = model.evaluate(vector)
        if not np.isfinite(value) or not np.isfinite(gradient).all() or abs(value-fit['objective']) > 1e-6:
            raise ValueError('coarse model value changed')
        problem = direct.continuation._Problem(model, vector, fixed_position=True,
                                                rf_arm=rf_arm, slope_half_width_hz_s=60)
        kkt = float(problem.stationarity(vector, gradient))
        feasible = bool(problem.feasible(vector))
        return dict(objective=float(value), stationarity=kkt, feasible=feasible,
                    qualified=feasible and kkt <= .001, rf_arm=rf_arm)
    def bounded(model, vector, **options):
        fit, diagnostics = direct.continuation.fit_bounded_position(model, np.asarray(vector, float).copy(), **options)
        return core.json_value(fit), core.json_value(diagnostics)
    def calibration(observations, bank, prior, trigger):
        model, fit = environment['verify_coarse'](observations, bank, prior, trigger['original'])
        point = [float(x) for x in trigger['key'].split(':')[1:]]
        handoff = transition(model, fit, point, arm, audit=audit, bounded=bounded,
                             qualify=direct.qualification.qualify)
        if handoff['promoted'] is None:
            return dict(status=handoff['status'], calibration=None, handoff=handoff)
        try:
            prefit = direct.validated_postfit(model, handoff['promoted'], np.asarray(point))
            after = direct.fresh_calibration(observations, model, prior,
                                             trigger['original']['bootstrap']['satellite_indices'], prefit)
        except (ValueError, AssertionError) as error:
            return dict(status='promoted-calibration-failed', calibration=None,
                        handoff=handoff, error=repr(error))
        return dict(after, handoff=handoff, direct_prefit=core.json_value(prefit))
    environment['recover_calibration'] = calibration
    return types.FunctionType(original.__code__, environment, original.__name__,
                              original.__defaults__, original.__closure__)
