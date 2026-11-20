"""Record exact terminal compact support and a local conditional information diagnostic."""

import json
import runpy
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

CHI95 = 5.991464547107979


def geometry(problem, pos, gates):
    import numpy as np

    x = np.asarray(pos)
    valid = [row for row in gates["tracks"] if row["compatible"]]
    baseline = problem.residual(x)
    step = 0.001  # km, the installed solver's finite-difference increment
    columns = []
    for axis in range(2):
        p = x.copy()
        p[axis] += step if x[axis] + step <= problem.upper[axis] else -step
        columns.append((problem.residual(p) - baseline) / (p[axis] - x[axis]))
    jacobian = np.column_stack(columns)
    if not np.isfinite(jacobian).all() or not np.isfinite(baseline).all():
        raise ValueError("nonfinite local residual differential")
    values = np.linalg.eigvalsh(jacobian.T @ jacobian)
    points = sum(row["points"] for row in valid)
    inflation = max(1.0, float(baseline @ baseline) / max(1, points - 2))
    rank2 = bool(values[0] > 0 and np.all(np.isfinite(values)))
    return dict(
        orbits=sorted({int(row["norad"]) for row in valid}),
        active_points=points,
        information_eigenvalues_per_km2=values.tolist(),
        nominal_radius95_km=float(np.sqrt(CHI95 * inflation / values[0])) if rank2 else None,
        information_condition=float(values[1] / values[0]) if rank2 else None,
        reduced_residual_inflation=inflation,
        east_north_km=x.tolist(),
    )


def main(root, args):
    entry = runpy.run_path(str(root / "__main__.py"))
    entry["activate"](root)
    from leo.analysis.localization_v3 import (
        event_position,
        family_cavity,
        history_position,
        predictive_linear,
        signed_context,
    )

    from tools.pipeline_eval.variants import v5_direct_cavity

    candidates, terminal = {}, {}
    saved_signed = signed_context.signed_context
    saved_cavity = family_cavity.cavity_policy
    original = history_position.retained_metrics

    def capture(problem, pos):
        gates = original(problem, pos)
        # Hold the very same gating list to prevent id reuse. It is used to
        # select support for the final accepted policy rather than a trial fit.
        if gates["tracks"]:
            try:
                diagnostic = geometry(problem, pos, gates)
            except (ArithmeticError, ValueError) as error:
                diagnostic = {"geometry_error": str(error)}
            candidates[id(gates)] = (gates, diagnostic)
        return gates

    def remember(pair):
        terminal.clear()
        for arm, result in pair.items():
            observed = candidates.get(id(result["gates"]))
            terminal[arm] = (
                dict(observed[1], latlon=list(result["endpoint_latlon"]))
                if observed is not None
                else None
            )

    def signed(*positional, **kwargs):
        d = saved_signed(*positional, **kwargs)
        remember(d["arms"])
        return d

    def cavity(*positional, **kwargs):
        d = saved_cavity(*positional, **kwargs)
        if d["status"] == "complete":
            remember(d["policy_arms"])
        return d

    with ExitStack() as stack:
        for module in (history_position, predictive_linear, event_position):
            stack.enter_context(patch.object(module, "retained_metrics", capture))
        stack.enter_context(patch.object(signed_context, "signed_context", signed))
        stack.enter_context(patch.object(family_cavity, "cavity_policy", cavity))
        result = v5_direct_cavity.run(**args)
    entry["verify_project_modules"](root)
    for arm, diagnostic in terminal.items():
        if diagnostic is not None and result["arms"][arm]["latlon"] != diagnostic["latlon"]:
            raise ValueError("local information does not bind to the final compact endpoint")
    result["metrics"]["terminal_local_geometry"] = terminal
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), json.loads(Path(sys.argv[2]).read_bytes()))
