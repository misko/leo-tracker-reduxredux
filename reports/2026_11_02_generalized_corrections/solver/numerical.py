"""Numerical-only fixed-point repair; no identities, priors or RF weights change."""
import time
import numpy as np
from scipy.optimize import minimize
from algo07_science import engine as e
from algo07_science.diagnose import objective
from phase_reference_checks import phase_refresh

BOUNDS = [(-12.5, 12.5)] * 2
GRADIENT_TOLERANCE = 1e-4


def gradient_probe(fun, x, steps=(.001, .01)):
    """Central differences and box-projected stationarity at two fixed scales."""
    x = np.asarray(x, float)
    gradients = []
    for step in steps:
        values = []
        for axis in np.eye(2):
            plus = np.minimum(12.5, x + axis * step)
            minus = np.maximum(-12.5, x - axis * step)
            width = float(np.linalg.norm(plus - minus))
            values.append((fun(plus) - fun(minus)) / width)
        gradients.append(np.asarray(values))
    projected = []
    for gradient in gradients:
        p = gradient.copy()
        p[(x <= -12.5 + 1e-8) & (p > 0)] = 0
        p[(x >= 12.5 - 1e-8) & (p < 0)] = 0
        projected.append(p)
    finite = bool(np.isfinite(gradients).all())
    discrepancy = float(np.max(abs(gradients[0] - gradients[1])))
    scale = max(GRADIENT_TOLERANCE, float(np.max(abs(gradients[1]))))
    stable = bool(finite and discrepancy <= max(1e-4, .25 * scale))
    return dict(steps_km=list(steps), gradients=gradients,
                projected_gradients=projected, finite=finite, stable=stable,
                gradient_discrepancy=discrepancy,
                projected_gradient_inf=float(np.max(abs(projected[0]))),
                tolerance=GRADIENT_TOLERANCE)


def baseline_diagnostic(d, arm):
    p, x = d['problems'][arm]
    _, phase = phase_refresh(np.asarray(p.state(x)['phases'])[p.labels], p.reference, limit_s=30.)
    probe = gradient_probe(lambda at: objective(p, d, at), x)
    reasons = []
    if phase['phase_change_s'] > .01:
        reasons.append('phase_not_closed')
    if probe['stable'] and probe['projected_gradient_inf'] > GRADIENT_TOLERANCE:
        reasons.append('stable_nonstationary_position')
    return dict(phase=phase, gradient=probe, trigger=bool(reasons), reasons=reasons)


def position_solve(fun, start, *, maxiter=35, maxfun=140, rescue_maxfun=140,
                   max_actual_calls=800):
    """Legacy solve, then central-Jacobian rescue for measured nonstationarity.

    All objective calls, including explicit Jacobians and diagnostic probes,
    count against one per-reference ceiling. No objective/prior is changed.
    """
    calls = 0
    class CallBudgetExceeded(Exception):
        pass
    def counted(at):
        nonlocal calls
        if calls >= max_actual_calls:
            raise CallBudgetExceeded('Per-reference objective-call ceiling')
        calls += 1
        return fun(at)
    def jacobian(at):
        at = np.asarray(at)
        values = []
        for axis in np.eye(2):
            plus=np.minimum(12.5,at+axis*.001)
            minus=np.maximum(-12.5,at-axis*.001)
            values.append((counted(plus)-counted(minus))/float(np.linalg.norm(plus-minus)))
        return np.asarray(values)
    initial = minimize(counted, np.asarray(start, float), method='L-BFGS-B', bounds=BOUNDS,
                       options=dict(maxiter=maxiter, maxfun=maxfun, eps=.001,
                                    ftol=1e-10, gtol=1e-4, maxls=15))
    chosen = initial
    probe = gradient_probe(counted, initial.x)
    abnormal = 'ABNORMAL' in str(initial.message).upper()
    attempt = bool((abnormal and probe['finite']) or (probe['stable'] and
                   probe['projected_gradient_inf'] > GRADIENT_TOLERANCE))
    rescue = None
    final_probe = probe
    if attempt:
        try:
            candidate = minimize(counted, np.asarray(initial.x), method='L-BFGS-B',
                                 jac=jacobian, bounds=BOUNDS,
                                 options=dict(maxiter=maxiter, maxfun=rescue_maxfun,
                                              ftol=0., gtol=1e-4, maxls=20))
            candidate_probe = gradient_probe(counted, candidate.x)
            if (candidate.success and np.isfinite(candidate.fun)
                    and candidate.fun <= initial.fun + 1e-7):
                chosen = candidate
                final_probe = candidate_probe
            rescue = dict(x=candidate.x, objective=float(candidate.fun),
                          success=bool(candidate.success), message=str(candidate.message),
                          nfev=int(candidate.nfev), gradient=candidate_probe,
                          adopted=chosen is candidate)
        except CallBudgetExceeded as exc:
            rescue = dict(success=False,message=str(exc),adopted=False,nfev=None)
    return chosen, dict(initial=dict(x=initial.x, objective=float(initial.fun),
                        success=bool(initial.success), message=str(initial.message),
                        nfev=int(initial.nfev), gradient=probe),
                        rescue_triggered=attempt, rescue=rescue,final_gradient=final_probe,
                        central_stationary=bool(final_probe['stable'] and final_probe['projected_gradient_inf']<=GRADIENT_TOLERANCE),
                        actual_objective_calls=calls,max_actual_calls=max_actual_calls,
                        total_optimizer_evaluations=int(initial.nfev) + ((rescue.get('nfev') or 0) if rescue else 0))


def fit(d, z, arm, *, start, reference, max_rounds=15, maxiter=35,
        maxfun=140, rescue_maxfun=140, max_actual_calls=800, checkpoint=None):
    x = np.array(start, float, copy=True)
    ref = np.array(reference, float, copy=True)
    history = []
    began = time.monotonic()
    for epoch in range(max_rounds):
        p, context = e.build(d, z, arm, ref)
        fun = lambda at: objective(p, context, at)
        opt, position = position_solve(fun, x, maxiter=maxiter, maxfun=maxfun,
                                       rescue_maxfun=rescue_maxfun,max_actual_calls=max_actual_calls)
        x = np.asarray(opt.x)
        actual = np.asarray(p.state(x)['phases'])[p.labels]
        clipped, check = phase_refresh(actual, ref, limit_s=30.)
        history.append(dict(epoch=epoch, x=x.copy(), reference=ref.copy(),
                            posterior_phase=actual, objective=fun(x),
                            success=bool(opt.success), message=str(opt.message),
                            position_solver=position, **check))
        if checkpoint:
            checkpoint(dict(status='fitting', arm=arm, history=history,
                            seconds=time.monotonic()-began))
        if check['phase_change_s'] <= .01:
            break
        if epoch < max_rounds-1:
            ref = ref + .5 * (clipped-ref)
    c = p.calculate(x)
    return dict(x=x, reference=p.reference.copy(), objective=fun(x),
                rms_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),
                phase_closed=bool(check['phase_change_s'] <= .01),
                phase_change_s=check['phase_change_s'], optimizer_success=bool(opt.success),
                boundary=bool(np.any(abs(x)>12.49)), history=history,
                central_stationary=position['central_stationary'],
                final_gradient=position['final_gradient'],
                final_inner_precision_change=float(c['final_log_precision_change']),
                seconds=time.monotonic()-began,
                total_position_evaluations=sum(h['position_solver']['total_optimizer_evaluations'] for h in history),
                actual_position_objective_calls=sum(h['position_solver']['actual_objective_calls'] for h in history),
                objective_scope='unchanged per-reference ALGO07 approximation; reference changes are not one invariant nonlinear objective')
