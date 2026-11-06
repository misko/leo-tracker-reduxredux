def bounded_gauss_newton(residual, initial, lower, upper, *, iterations=24, step=0.001):
    """Damped finite-difference least squares with explicit bounded iterates.

    Parameters must be scaled by the caller. The reported history records
    accepted iterates, including their objective, never a GPS accuracy test.
    """
    x, lo, hi = (np.asarray(a, float) for a in (initial, lower, upper))
    if x.ndim != 1 or lo.shape != x.shape or hi.shape != x.shape:
        raise ValueError('matching one-dimensional parameter bounds required')
    if np.any(lo >= hi) or step <= 0 or iterations < 1:
        raise ValueError('ordered bounds and positive numerical budgets required')
    x = np.clip(x, lo, hi)
    r = residual(x)
    score, damping, evaluations = (float(r @ r), 0.01, 1)
    history = [dict(parameters=x.copy(), score=score)]
    stopped = 'iteration_budget'
    for _ in range(iterations):
        columns = []
        columns = _columns(residual, x, lo, hi, step)
        evaluations += 2 * len(x)
        jacobian = np.array(columns).T
        normal, gradient = (jacobian.T @ jacobian, jacobian.T @ r)
        diagonal = np.maximum(np.diag(normal), 1e-06)
        accepted = False
        for _trial in range(9):
            delta = np.linalg.solve(normal + damping * np.diag(diagonal), -gradient)
            proposal = np.clip(x + delta, lo, hi)
            rr = residual(proposal)
            evaluations += 1
            candidate = float(rr @ rr)
            if candidate < score - 1e-09:
                improvement = score - candidate
                x, r, score = (proposal, rr, candidate)
                history.append(dict(parameters=x.copy(), score=score))
                damping = max(1e-07, damping / 3)
                accepted = True
                if np.linalg.norm(delta[:2]) < 0.0001 and improvement < 1e-05:
                    stopped = 'small_step_and_improvement'
                break
            damping *= 5
        if not accepted:
            stopped = 'no_accepted_damped_step'
            break
        if stopped == 'small_step_and_improvement':
            break
    return dict(parameters=x, score=score, history=history, evaluations=evaluations, stopped=stopped)