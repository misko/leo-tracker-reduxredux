"""Bounded fixed-group IRLS with full physical mixture line search."""
import time
import numpy as np


def fit(model, initial, deadline, max_iterations=64):
    x = np.array(initial, copy=True); history = []; reason = 'iteration_limit'; converged = False
    for iteration in range(max_iterations+1):
        if time.monotonic() >= deadline: reason = 'wall_budget'; break
        value, gradient, metric, _ = model.evaluate(x)
        if not history: history.append(value)
        step = -np.linalg.solve(metric, gradient)
        decrement = float(-gradient@step)
        if decrement < 1e-8: converged = True; reason = 'stationary'; break
        if iteration == max_iterations: break
        length = np.linalg.norm(step[:2])
        if length > 25: step *= 25/length
        accepted = False
        for k in range(18):
            trial = x.copy(); trial[model.active] += step*2.**(-k)
            if np.linalg.norm(trial[:2]) > 250: continue
            try: candidate = model.evaluate(trial, False)[0]
            except (ValueError, np.linalg.LinAlgError): continue
            if np.isfinite(candidate) and candidate < value:
                x = trial; history.append(candidate); accepted = True; break
        if not accepted: reason = 'line_search_stalled'; break
    return dict(mean=x.tolist(), objectives=history, converged=converged, reason=reason, iterations=iteration)


def audit(model, result):
    errors = []; details = {}
    try:
        assert result['converged'], result['reason']
        x = np.asarray(result['mean']); assert np.isfinite(x).all() and np.linalg.norm(x[:2]) <= 250
        value, gradient, metric, _ = model.evaluate(x)
        assert abs(value-result['objectives'][-1]) < 1e-6
        assert np.all(np.diff(result['objectives']) <= 1e-6)
        numeric = []
        for j in model.active:
            step = np.zeros(len(x)); step[j] = .0005
            numeric.append((model.evaluate(x+step, False)[0]-model.evaluate(x-step, False)[0])/.001)
        numeric = np.asarray(numeric)
        details = dict(gradient_error=float(np.max(abs(gradient-numeric))), decrement_squared=float(numeric@np.linalg.solve(metric, numeric)))
        assert details['gradient_error'] < .005 and details['decrement_squared'] < 1e-5, str(details)
    except (AssertionError, ValueError, np.linalg.LinAlgError) as error: errors.append(type(error).__name__+': '+str(error))
    return dict(accepted=not errors, failures=errors, **details)
