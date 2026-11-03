"""Bounded Gauss-Newton on small, explicitly mapped numerical factors."""

import numpy as np


def factor_gauss_newton(functions, mappings, initial, lower, upper, *, iterations=24):
    """Assemble only each factor's local Jacobian; share indexed parameters.

    A shared orbit correction may appear in several factors without evaluating
    unrelated factors for its numerical derivative. Priors belong to callers.
    """
    x, lo, hi = (np.asarray(v, float) for v in (initial, lower, upper))
    maps = [np.asarray(v, int) for v in mappings]
    if len(functions) != len(maps) or x.shape != lo.shape or x.shape != hi.shape:
        raise ValueError("matching factors, parameter maps and bounds required")
    if np.any(lo >= hi) or iterations < 1:
        raise ValueError("ordered bounds and positive iteration budget required")
    for m in maps:
        if len(set(m)) != len(m) or np.any(m < 0) or np.any(m >= len(x)):
            raise ValueError("unique valid parameter indices per factor required")
    x = np.clip(x, lo, hi)
    residuals = [f(x[m]) for f, m in zip(functions, maps, strict=True)]
    score = sum(float(r @ r) for r in residuals)
    history, damping, evaluations = [dict(parameters=x.copy(), score=score)], 1e-2, len(maps)
    stop = "iteration_budget"
    for _ in range(iterations):
        normal, rhs = np.zeros((len(x), len(x))), np.zeros(len(x))
        for f, m, r in zip(functions, maps, residuals, strict=True):
            columns = []
            for k, global_k in enumerate(m):
                a, b = x[m].copy(), x[m].copy()
                a[k] = max(lo[global_k], a[k] - 1e-3)
                b[k] = min(hi[global_k], b[k] + 1e-3)
                columns.append((f(b) - f(a)) / (b[k] - a[k]))
                evaluations += 2
            jac = np.array(columns).T
            normal[np.ix_(m, m)] += jac.T @ jac
            rhs[m] += jac.T @ r
        diagonal = np.maximum(np.diag(normal), 1e-6)
        accepted = False
        for _trial in range(9):
            delta = np.linalg.solve(normal + damping * np.diag(diagonal), -rhs)
            proposal = np.clip(x + delta, lo, hi)
            rr = [f(proposal[m]) for f, m in zip(functions, maps, strict=True)]
            evaluations += len(maps)
            candidate = sum(float(r @ r) for r in rr)
            if candidate < score - 1e-9:
                improvement = score - candidate
                x, residuals, score = proposal, rr, candidate
                history.append(dict(parameters=x.copy(), score=score))
                damping = max(1e-7, damping / 3)
                accepted = True
                if np.linalg.norm(delta[:2]) < 1e-4 and improvement < 1e-5:
                    stop = "small_step_and_improvement"
                break
            damping *= 5
        if not accepted:
            stop = "no_accepted_damped_step"
            break
        if stop == "small_step_and_improvement":
            break
    return dict(parameters=x, score=score, history=history, evaluations=evaluations, stopped=stop)
