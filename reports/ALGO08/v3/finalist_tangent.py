"""A geometry-only horizontal tangent for the original robust cold residual."""

from collections import Counter, OrderedDict
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np
from scipy.linalg import cho_factor, cho_solve


OPTIMIZER_PIN = "5bceea78eaece66c20f1e12c1fd109182a8cc5cc2e8b6d410f2d68d93e9110a3"


def nuisance_tangent(u, y, du, dy, coefficient, precision, volume, factor, inverse):
    """Differentiate the conditional normal equations at fixed robust precisions."""
    residual = y - u @ coefficient
    direct = dy - du @ coefficient
    response = du.T @ residual + u.T @ direct
    db = cho_solve(factor, response, check_finite=False)
    innovation = direct - u @ db
    # d log det(H) = trace(H^-1 (du.T @ u + u.T @ du)).
    # This row contraction leaves the fixed prior log determinant unchanged.
    dvolume = float(np.einsum("ij,ij->", inverse, du)) / np.sqrt(volume) if volume > 0. else 0.
    return innovation, db * np.sqrt(precision), dvolume


class HorizontalTangent:
    def __init__(self, problem, checked_type, geometry, points):
        if type(problem) is not checked_type or hasattr(problem, "events") or problem.variant != "radio_noise":
            raise ValueError("Expected the fixed-owner normal cold likelihood")
        self.problem = problem
        self.geometry = geometry
        self.points = points
        self.keep = problem.keep
        self.group = problem.noise_groups[self.keep]
        self.states = OrderedDict()
        self.stats = Counter()

    def watch(self, operation):
        def evaluate(x):
            result = operation(x)
            self.states[np.asarray(x, np.float64).tobytes()] = {
                key: result[key] for key in ("coefficient", "coefficient_prior_precision", "noise_precision", "logvolume")
            }
            if len(self.states) > 12:
                self.states.popitem(last=False)
            return result
        return evaluate

    def __call__(self, x, lo, hi, step, r):
        start = process_time_ns()
        result = self.propose(x, lo, hi, step, r)
        self.stats["tangent_cpu_ns"] += process_time_ns() - start
        self.stats["tangent_attempts"] += 1
        self.stats["tangents"] += result is not None
        return result

    def propose(self, x, lo, hi, step, r):
        previous = self.states.get(x.tobytes())
        if previous is None or np.any(np.minimum(x-lo, hi-x) <= step):
            self.stats["centre_or_bound_fallbacks"] += 1
            return None
        model = self.problem
        centre = self.geometry(model, x, geometry_only=True)
        neighbours = [(self.geometry(model, point, geometry_only=True), delta)
                      for _, point, delta in self.points(x, lo, hi, step)]
        self.stats["geometry_only_calls"] += 1 + len(neighbours)
        base_zenith = centre["elevation"][self.keep]
        if any(np.any((other["elevation"][self.keep] < 0.) != (base_zenith < 0.)) for other, _ in neighbours):
            self.stats["horizon_fallbacks"] += 1
            return None
        w = np.sqrt(previous["noise_precision"][self.group]) / model.point_noise[self.keep]
        p = previous["coefficient_prior_precision"]
        a = previous["coefficient"]
        volume = previous["logvolume"]
        u = centre["features"][self.keep] * w[:, None]
        y = (model.values - model.q * centre["intercept"])[self.keep] * w
        n, m = u.shape
        if r.size < 2*n+m+2 or not np.allclose(r[:n], y-u@a, rtol=1e-9, atol=1e-9):
            self.stats["residual_layout_fallbacks"] += 1
            return None
        normal = u.T @ u
        normal.flat[::m+1] += p
        try:
            factor = cho_factor(normal, lower=True, check_finite=False)
            diag = np.diag(factor[0])
            if not np.isfinite(diag).all() or diag.min()/diag.max() < 1e-6:
                self.stats["condition_fallbacks"] += 1
                return None
            inverse_rows = cho_solve(factor, u.T, check_finite=False).T
        except np.linalg.LinAlgError:
            self.stats["condition_fallbacks"] += 1
            return None
        columns = np.zeros((r.size, 2))
        for index, (other, delta) in enumerate(neighbours):
            du = (other["features"][self.keep] - centre["features"][self.keep]) * (w/delta)[:, None]
            dy = (-model.q * (other["intercept"] - centre["intercept"]))[self.keep] * (w/delta)
            dr, db, dv = nuisance_tangent(u, y, du, dy, a, p, volume, factor, inverse_rows)
            columns[:n, index] = dr
            columns[n:n+m, index] = db
            columns[n+m, index] = dv
            columns[-n:, index] = ((np.maximum(0., -other["elevation"][self.keep])
                                      - np.maximum(0., -base_zenith)) / (2.*delta))
        if not np.isfinite(columns).all():
            self.stats["condition_fallbacks"] += 1
            return None
        return columns


def change_optimizer(original, tangent, audit):
    """Replace only derivative proposals in the pinned released control flow."""
    file = Path(original.__code__.co_filename)
    if sha256(file.read_bytes()).hexdigest() != OPTIMIZER_PIN:
        raise ValueError("Unexpected bounded secant source")
    source = getsource(original)
    replacements = (
        ("    def linearize():\n        nonlocal evaluations, refreshes\n",
         "    approximate, force_exact_next = False, False\n\n"
         "    def linearize(force=False):\n        nonlocal evaluations, refreshes, approximate\n"
         "        proposal = None if force else _tangent(x, lo, hi, step, r)\n"
         "        approximate = proposal is not None\n"
         "        if approximate:\n            refreshes += 1\n            return proposal\n"
         "        _audit['exact_linearizations'] += 1\n"),
        ("        fresh = jacobian is None\n        if fresh:\n            jacobian, updates = linearize(), 0\n",
         "        fresh, saved_radius = jacobian is None, radius\n        if fresh:\n"
         "            jacobian, updates = linearize(force_exact_next), 0\n"
         "            force_exact_next = False\n"),
        ("        if np.linalg.norm(full) <= STOP_KM and not fresh:\n"
         "            jacobian, updates, fresh = linearize(), 0, True\n",
         "        if np.linalg.norm(full) <= STOP_KM and (not fresh or approximate):\n"
         "            jacobian, updates, fresh = linearize(True), 0, True\n"),
        ("        else:\n            if fresh:\n                stopped = \"no_accepted_trust_step\"\n",
         "        else:\n            if fresh and approximate:\n"
         "                jacobian, force_exact_next, radius = None, True, saved_radius\n"
         "                _audit['exact_retries'] += 1\n"
         "                continue\n"
         "            if fresh:\n                stopped = \"no_accepted_trust_step\"\n"),
    )
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError("Pinned secant proposal/terminal boundary changed")
        source = source.replace(before, after)
    namespace = dict(original.__globals__, _tangent=tangent, _audit=audit)
    exec(compile(source, str(file), "exec"), namespace)
    return namespace[original.__name__]


def derivative_checks(tangent, residual, point):
    """Compare the proposal with released residual differences off the timed path."""
    problem, h = tangent.problem, 1e-3
    centre = residual(point)
    proposed = tangent.propose(point, problem.lower, problem.upper, h, centre)
    if proposed is None:
        return dict(eligible=False)
    columns = [(residual(x) - centre)/delta for _, x, delta in tangent.points(point, problem.lower, problem.upper, h)]
    exact = np.column_stack(columns)
    a, b = proposed.T @ centre, exact.T @ centre
    norms = float(np.linalg.norm(a)*np.linalg.norm(b))
    return dict(eligible=True, relative_jacobian_error=float(np.linalg.norm(proposed-exact)/np.linalg.norm(exact)),
                approximate_gradient=a, exact_gradient=b, gradient_cosine=float(a@b/norms) if norms else None)


def measured_optimizer(original, mode, traces):
    from leo.analysis.localization_v3.marginal import JointMarginal
    from leo.analysis.localization_v3.position import NormalPosition

    def solve(residual, *args, **kwargs):
        started = process_time_ns()
        clock, calls = Counter(), []

        def recorded(point):
            tick = process_time_ns()
            exact = residual(point)
            calls.append(dict(point=point.copy(), score=float(exact @ exact), cpu_ns=process_time_ns()-tick))
            return exact

        if mode == "control":
            optimized = original(recorded, *args, **kwargs)
        else:
            problem = residual.__self__
            tangent = HorizontalTangent(problem, NormalPosition, JointMarginal.calculate, original.__globals__["_forward_points"])
            candidate = change_optimizer(original, tangent, clock)
            with patch.object(problem, "calculate", tangent.watch(problem.calculate)):
                optimized = candidate(recorded, *args, **kwargs)
            clock.update(tangent.stats)
        if len(calls) != optimized["evaluations"]:
            raise ValueError("The scoped optimizer did not count all full robust requests")
        timed = process_time_ns()-started
        diagnostic, diagnostic_cpu = [], 0
        if mode != "control":
            check = process_time_ns()
            with patch.object(problem, "calculate", tangent.watch(problem.calculate)):
                for point in (optimized["history"][0]["parameters"], optimized["parameters"]):
                    diagnostic.append(derivative_checks(tangent, residual, point))
            diagnostic_cpu = process_time_ns()-check
        traces.append(dict(cpu_ns=timed, result=optimized, proposals=dict(clock), full_calls=calls,
                           derivative_checks=diagnostic, derivative_checks_cpu_ns=diagnostic_cpu))
        return optimized
    return solve
