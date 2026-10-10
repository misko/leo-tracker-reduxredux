"""Six-call conditional callback diagnostic; no loader, fit, or reference port."""
import time
import numpy as np


def evidence(value):
    if isinstance(value, np.ndarray):
        return evidence(value.tolist())
    if isinstance(value, np.generic):
        return evidence(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {key: evidence(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [evidence(item) for item in value]
    return value


def check(model, vector, coefficients, *, arm, stored_objective,
          conditional_factory, feasible, stored_joint_objective=None,
          anchor_audit=None, fingerprint=None, clock=time.monotonic):
    """Inject152 ConditionalModes and an independent physical feasibility port.

    The30-second soft deadline starts before validation/construction and is checked
    before each physical audit and objective attempt. An in-flight callback is not
    interrupted. Objective failures count against the six-attempt cap. No retries.
    """
    begun = clock()
    receipt = dict(status='failed', joint_attempts=0, calls=[], initial_audit=None,
                   steps=None, derivatives=[], additive=None, anchor=None,
                   elapsed_s=None, live_anchor_audit=None,
                   scope='Numerical callback diagnostic; no accuracy claim')
    try:
        anchor_vector = np.array(vector, dtype=float, copy=True)
        anchor_clock = np.array(coefficients, dtype=float, copy=True)
        if arm not in ('fitted-c', 'zero-c'):
            raise ValueError('unknown final c arm')
        if not np.isfinite(stored_objective):
            raise ValueError('nonfinite stored objective')
        if anchor_vector.ndim != 1 or anchor_vector.size < 8 or anchor_clock.ndim != 1:
            raise ValueError('invalid state shape')
        if not np.isfinite(anchor_vector).all() or not np.isfinite(anchor_clock).all():
            raise ValueError('nonfinite anchor')
        if arm == 'zero-c' and (anchor_vector[6] != 0 or np.any(anchor_clock[-2:] != 0)):
            raise ValueError('zero-c locks violated')
        expected_clock = anchor_clock.copy()
        label = 'anchor'
        original_fingerprint = evidence(fingerprint()) if fingerprint is not None else None
        receipt['inference_fingerprint'] = original_fingerprint

        def unchanged():
            current = evidence(fingerprint()) if fingerprint is not None else None
            if current != original_fingerprint:
                raise ValueError('original inference arrays mutated')
            return current

        def deadline():
            if clock() - begun >= 30:
                raise TimeoutError('30-second soft preflight budget exhausted')

        def audit(v, c):
            deadline()
            result = feasible(v.copy(), c.copy())
            receipt['last_physical_audit'] = evidence(result)
            ok = result.get('feasible') if isinstance(result, dict) else result
            if not bool(ok):
                raise ValueError('independent physical feasibility rejected state')
            unchanged()
            return result

        receipt['initial_audit'] = evidence(audit(anchor_vector, anchor_clock))

        class GuardedModel:
            def __getattr__(self, name):
                return getattr(model, name)

            def evaluate_joint(self, v, c):
                if receipt['joint_attempts'] >= 6:
                    raise ValueError('six objective attempt cap exceeded')
                event = dict(label=label, elapsed_s=None, called=False, audit=None)
                receipt['calls'].append(event)
                receipt['joint_attempts'] += 1
                start = clock()
                try:
                    deadline()
                    if not np.array_equal(v, anchor_vector) or not np.array_equal(c, expected_clock):
                        raise ValueError('conditional callback changed fixed state')
                    if arm == 'zero-c' and (v[6] != 0 or np.any(c[-2:] != 0)):
                        raise ValueError('conditional zero-c locks changed')
                    event['audit'] = evidence(audit(np.asarray(v), np.asarray(c)))
                    deadline()
                    event['fingerprint_before'] = unchanged()
                    event['called'] = True
                    objective_begun = clock()
                    try:
                        value, physical_gradient, clock_gradient, auxiliary = model.evaluate_joint(v.copy(), c.copy())
                    finally:
                        event['objective_elapsed_s'] = clock() - objective_begun
                    event['fingerprint_after'] = evidence(fingerprint()) if fingerprint is not None else None
                    unchanged()
                    physical_gradient, clock_gradient = np.asarray(physical_gradient), np.asarray(clock_gradient)
                    if (not np.isfinite(value) or physical_gradient.shape != anchor_vector.shape
                            or clock_gradient.shape != anchor_clock.shape
                            or not np.isfinite(physical_gradient).all()
                            or not np.isfinite(clock_gradient).all()):
                        raise ValueError('nonfinite or invalid objective callback')
                    event.update(value=float(value), physical_gradient=physical_gradient.copy(),
                                 clock_gradient=clock_gradient.copy())
                    return value, physical_gradient.copy(), clock_gradient.copy(), auxiliary
                except Exception as error:
                    event['error'] = repr(error)
                    if fingerprint is not None:
                        try:
                            event['fingerprint_after'] = evidence(fingerprint())
                            event['inference_unchanged'] = event['fingerprint_after'] == original_fingerprint
                        except Exception as fingerprint_error:
                            event['fingerprint_error'] = repr(fingerprint_error)
                    raise
                finally:
                    event['elapsed_s'] = clock() - start

        deadline()
        modes = conditional_factory(GuardedModel(), anchor_vector.copy(), anchor_clock.copy(), arm=arm)
        if receipt['joint_attempts'] != 1:
            raise ValueError('conditional construction must make exactly one anchor call')
        anchor = float(modes.anchor_value)
        receipt['anchor'] = dict(value=anchor, stored_objective=float(stored_objective),
                                 difference=anchor-stored_objective)
        if abs(anchor-stored_objective) > 1e-6:
            raise ValueError('stored anchor objective changed')
        receipt['anchor']['stored_joint_objective'] = stored_joint_objective
        if stored_joint_objective is not None:
            if not np.isfinite(stored_joint_objective) or abs(anchor-stored_joint_objective)>1e-6:
                raise ValueError('stored joint-state total changed')
        if anchor_audit is not None:
            deadline()
            anchor_call=receipt['calls'][0]
            result=anchor_audit(anchor_vector.copy(),anchor_clock.copy(),
                                np.asarray(anchor_call['physical_gradient']).copy(),
                                np.asarray(anchor_call['clock_gradient']).copy(),arm)
            receipt['live_anchor_audit']=evidence(result)
            if not result.get('qualified',False):
                raise ValueError('independent live anchor qualification failed')
        if not np.isfinite(modes.precision) or modes.precision <= 0:
            raise ValueError('invalid lowest prior precision')
        steps = []
        for r in (0, 1):
            amplitude = float(modes.amplitudes[r])
            lower, upper = modes.intervals[r]
            margin = min(amplitude-lower, upper-amplitude)
            h = min(.001 / np.sqrt(modes.precision), .25*margin)
            tiny = 64*np.finfo(float).eps*max(1., abs(amplitude))
            if not np.isfinite(h) or h < 1e-6 or h <= tiny:
                raise ValueError('boundary, nonpositive or numerically tiny central step')
            steps.append(float(h))
        receipt['steps'] = steps
        positives = []
        positive_clocks = []
        for r, h in enumerate(steps):
            values = []
            for sign in (1, -1):
                label = f'receiver-{r}-' + ('plus' if sign == 1 else 'minus')
                expected_clock = anchor_clock.copy()
                target=modes.amplitudes[r] + sign*h
                expected_clock[modes.slices[r]] += modes.direction*(target-modes.amplitudes[r])
                result = modes.scalar(r, target)
                values.append(float(result['value']))
                if sign == 1:
                    positive_clocks.append(expected_clock.copy())
            positives.append(values[0])
            numerical = (values[0]-values[1])/(2*h)
            projected = float(modes.direction @ modes.anchor_clock_gradient[modes.slices[r]])
            tolerance = 1e-5 + 1e-4*abs(projected)
            record = dict(receiver=r, central=numerical, projected=projected,
                          difference=numerical-projected, tolerance=tolerance)
            receipt['derivatives'].append(record)
            if not np.isfinite(numerical) or abs(numerical-projected) > tolerance:
                raise ValueError('projected gradient disagrees with central derivative')
        label = 'combined-plus'
        expected_clock = anchor_clock.copy()
        for r in (0, 1):
            expected_clock[modes.slices[r]] = positive_clocks[r][modes.slices[r]]
        receipt['positive_clock_deltas'] = [c-anchor_clock for c in positive_clocks]
        combined = float(GuardedModel().evaluate_joint(anchor_vector.copy(), expected_clock.copy())[0])
        predicted = positives[0]+positives[1]-anchor
        receipt['additive'] = dict(combined=combined, predicted=predicted,
                                   difference=combined-predicted, tolerance=1e-6)
        if abs(combined-predicted) > 1e-6:
            raise ValueError('receiver conditional value factorization failed')
        receipt['status'] = 'passed'
    except Exception as error:
        receipt['error'] = repr(error)
    finally:
        receipt['elapsed_s'] = clock() - begun
    return evidence(receipt)
