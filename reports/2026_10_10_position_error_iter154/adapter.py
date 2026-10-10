"""Own-arm admission followed by unchanged150 recovery; no global mutation."""
import time
import types

from own_arm import repair_then_transition


def recovery_port(backend, arm, transition150):
    original = backend['recovered_region']
    environment = dict(original.__globals__)
    direct, np, core = environment['direct'], environment['np'], environment['core']

    def audit(model, fit, rf_arm):
        vector = np.asarray(fit['vector'], float)
        value, gradient, _ = model.evaluate(vector)
        if not np.isfinite(value) or not np.isfinite(gradient).all():
            raise ValueError('nonfinite independent coarse audit')
        if abs(value - fit['objective']) > 1e-6:
            raise ValueError('coarse objective changed')
        problem = direct.continuation._Problem(
            model, vector, fixed_position=True, rf_arm=rf_arm,
            slope_half_width_hz_s=60,
        )
        stationarity = float(problem.stationarity(vector, gradient))
        feasible = bool(problem.feasible(vector))
        return dict(objective=float(value), stationarity=stationarity,
                    feasible=feasible, qualified=feasible and stationarity <= .001,
                    rf_arm=rf_arm)

    def bounded(model, vector, **options):
        fit, diagnostics = direct.continuation.fit_bounded_position(
            model, np.asarray(vector, float).copy(), **options
        )
        return core.json_value(fit), core.json_value(diagnostics)

    def calibration(observations, bank, prior, trigger):
        begun = time.monotonic()
        try:
            model, fit = environment['verify_coarse'](
                observations, bank, prior, trigger['original']
            )
        except (ValueError, AssertionError, RuntimeError) as error:
            return dict(status='original-reconstruction-failed', calibration=None,
                        original=trigger['original'], error=repr(error))
        point = [float(x) for x in trigger['key'].split(':')[1:]]
        costs = []
        phase = 'own-arm'
        def timed_audit(model, fit, rf_arm):
            start = time.monotonic()
            try:
                return audit(model, fit, rf_arm)
            finally:
                costs.append(dict(phase=phase, operation='audit', rf_arm=rf_arm,
                                  elapsed_s=time.monotonic() - start))
        def timed_bounded(model, vector, **options):
            start = time.monotonic()
            try:
                return bounded(model, vector, **options)
            finally:
                costs.append(dict(phase=phase, operation='bounded-fit',
                                  rf_arm=options['rf_arm'],
                                  elapsed_s=time.monotonic() - start))
        def handoff(model, admitted, point, arm):
            nonlocal phase
            phase = '150-transition'
            start=time.monotonic()
            try:
                return transition150.transition(
                    model, admitted, point, arm, audit=timed_audit, bounded=timed_bounded,
                    qualify=direct.qualification.qualify,
                )
            finally:
                costs.append(dict(phase=phase,operation='transition-total',elapsed_s=time.monotonic()-start))
        own = repair_then_transition(
            model, fit, point, arm, audit=timed_audit, bounded=timed_bounded, transition=handoff
        )
        own['elapsed_s'] = time.monotonic() - begun
        own['cost_events'] = costs
        own['own_arm_audit_elapsed_s']=sum(e['elapsed_s'] for e in costs if e['phase']=='own-arm' and e['operation']=='audit')
        own['own_arm_repair_elapsed_s']=sum(e['elapsed_s'] for e in costs if e['phase']=='own-arm' and e['operation']=='bounded-fit')
        own['transition150_elapsed_s']=next((e['elapsed_s'] for e in costs if e['operation']=='transition-total'),None)
        downstream = own.get('handoff')
        if not downstream or downstream.get('promoted') is None:
            return dict(status=downstream['status'] if downstream else own['status'],
                        calibration=None, own_arm=own)
        try:
            prefit = direct.validated_postfit(model, downstream['promoted'], np.asarray(point))
            after = direct.fresh_calibration(
                observations, model, prior,
                trigger['original']['bootstrap']['satellite_indices'], prefit,
            )
        except (ValueError, AssertionError, RuntimeError) as error:
            return dict(status='promoted-calibration-failed', calibration=None,
                        own_arm=own, handoff=downstream, error=repr(error))
        return dict(after, own_arm=own, handoff=downstream,
                    direct_prefit=core.json_value(prefit))

    environment['recover_calibration'] = calibration
    return types.FunctionType(original.__code__, environment, original.__name__,
                              original.__defaults__, original.__closure__)
