"""Fixed-position successor of immutable161 audit, using narrow injected ports."""

import importlib.util
from pathlib import Path
import time

import numpy as np

PATH = Path(__file__).resolve().parents[1] / "2026_10_10_position_error_iter161/fit_core.py"
SPEC = importlib.util.spec_from_file_location("fit_core161_for162", PATH)
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)
plain = BASE.plain


def execute_cell(objective, common_vector, common_clock, *, arm, fit_port,
                 problem_type, clock=time.monotonic):
    """Only position differs from the common original zero-c nuisance start.

    The unchanged161 core retains solver failures, fresh objective parity,
    clock boxes/locks, budgets and costs. The two injected adapters below force
    fixed position in BOTH the fitter and physical KKT parameterization. Exact
    coordinate equality is an additional admission gate, not a replacement for
    original physical feasibility. No unconstrained spatial stationarity is
    demanded; no projected position is adopted.
    """
    seed = np.array(common_vector, dtype=float, copy=True)
    position = seed[:2].copy()

    def bounded_fit(model, supplied, **options):
        options["fixed_position"] = True
        return fit_port(model, supplied, **options)

    def fixed_problem(model, supplied, **options):
        options["fixed_position"] = True
        problem = problem_type(model, supplied, **options)

        class PhysicalAudit:
            def feasible(self, vector):
                return bool(np.array_equal(np.asarray(vector)[:2], position)
                            and problem.feasible(vector))

            def stationarity(self, vector, gradient):
                return problem.stationarity(vector, gradient)

        return PhysicalAudit()

    result = BASE.execute_cell(objective, seed, common_clock, arm=arm,
                               fit_port=bounded_fit, problem_type=fixed_problem, clock=clock)
    result["fixed_position"] = True
    result["hypothesis_position"] = plain(position)
    if result.get("audit") is not None:
        returned = np.asarray(result["solver"]["vector"])
        result["audit"]["position_locked"] = bool(np.array_equal(returned[:2], position))
    return result
