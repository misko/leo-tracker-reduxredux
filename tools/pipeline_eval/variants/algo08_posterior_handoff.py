"""Whiten a research grid's predictive rows from the checked native posterior."""

import ctypes as ct
import subprocess
from collections import Counter
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np
from scipy.linalg import solve_triangular

from leo.analysis.localization_v3 import event_position, history_position, predictive_linear, recovery_inventory
from leo.analysis.localization_v4 import native_bound


SOURCE_SHA256 = "40888d6143f385c2146e5e2cb28ea99a96b2f1bb791fab4c22b5afaaa2b3a23b"
PYTHON_SHA256 = {
    "attach_event_predictive": "f85ee55692b3f18a535582c4bdef14dbba901e98f82d81aa6239f03880f13e5a",
    "make_problem": "61b0e7eeac5052102e619247b816ea69c1b4c0eecfc97197b46d111a1561e5a6",
    "scale_posterior": "9f499c3b0512c2bf9ef39f076c14c2bb3bdb245deb3681e954e195052ed5837b",
}


def replace(source, anchor, replacement):
    if source.count(anchor) != 1:
        raise ValueError("Expected one pinned posterior handoff boundary")
    return source.replace(anchor, replacement)


def build(output):
    if native_bound.digest(native_bound.SOURCE) != SOURCE_SHA256:
        raise ValueError("Expected the reviewed native bound source")
    source = native_bound.SOURCE.read_text()
    header = Path(__file__).with_suffix(".h").read_text()
    source = replace(source, "/* All work belongs", header + "\n/* All work belongs")
    source = replace(source, "int nb_run(", "int nb_run_posterior(")
    source = replace(source, "int *updates,double *returned_rates) {", """int *updates,
 double *returned_rates,int export_width,double *lower,int32_t *order,int *exported) {
    *exported=0;""")
    source = replace(source, "        if(final)break;", """
        if(final) {
            if (p==export_width && lower && order)
                *exported=export_posterior(l,d,e,root,precision,lower,order);
            break;
        }""")
    output = Path(output)
    with output.with_suffix(".c").open("x") as generated:
        generated.write(source)
    subprocess.run(["cc", *native_bound.FLAGS, "-Wall", "-Wextra", "-Werror",
                    str(output.with_suffix(".c")), "-lm", "-o", str(output)],
                   check=True, timeout=30)


class Capture:
    def __init__(self, width):
        self.width = width
        self.lower = np.empty((width, width))
        self.order = np.empty(width, np.int32)
        self.bound = None
        self.accepted = -1
        self.exported = ct.c_int()

    def run(self, owner, operation, args):
        self.bound = owner
        self.accepted = owner.counts["activated"]
        return operation(*args, self.width, native_bound.pointer(self.lower),
                         native_bound.pointer(self.order), ct.byref(self.exported))

    def valid(self):
        return (self.exported.value == 1 and self.bound.counts["activated"] == self.accepted + 1
                and np.isfinite(self.lower).all() and np.all(self.lower.diagonal() > 0)
                and np.array_equal(np.sort(self.order), np.arange(self.width)))


def whiten(design, lower, order, original_scales):
    # The native factor is in the latent scales used to fit the curved rows.
    # Predictive coefficients are in the original scales used for reporting.
    rhs = (design[:, order] * original_scales[order]).T
    return solve_triangular(lower, rhs, lower=True, check_finite=False).T


def predictive_factor(raw, design, sigma, groups, capture, member_count):
    scales = np.ones(capture.width)
    scales[-member_count:] = 0.3
    uncertainty = whiten(design, capture.lower, capture.order, scales)
    biases = np.zeros((len(raw), int(groups.max()) + 1))
    biases[np.arange(len(raw)), groups] = 300.
    features = np.column_stack((uncertainty, biases))
    ones = np.ones(len(raw))
    return predictive_linear.conditional_gaussian(
        raw, features, sigma, ones, ones, np.ones(features.shape[1]), 1.)


def bind_export(compiled, owner):
    stock = owner.run
    compiled.argtypes = stock.argtypes + [ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_void_p]
    compiled.restype = stock.restype
    return stock


def check_python(*functions):
    for operation in functions:
        if sha256(getsource(operation).encode()).hexdigest() != PYTHON_SHA256[operation.__name__]:
            raise ValueError(f"Incompatible posterior handoff source: {operation.__name__}")


@contextmanager
def grid_handoff(port, library, in_grid):
    """Swap one attached predictive evaluator only while scoring grid points."""
    source = event_position.attach_event_predictive
    check_python(source, history_position.make_problem, history_position.scale_posterior)
    compiled = None if library is None else ct.CDLL(str(library)).nb_run_posterior
    original_bound = port.NativeBound
    counts = Counter()
    pending = None

    def factory(*args, **kwargs):
        owner = original_bound(*args, **kwargs)
        stock = bind_export(compiled, owner)

        def run(*args):
            if pending is None or pending.bound is not None:
                return stock(*args)
            return pending.run(owner, compiled, args)

        owner.run = run
        return owner

    def grid_prediction(p, curved, position, view, powers, values, sigma, groups, design):
        nonlocal pending
        start = process_time_ns()
        pending = (Capture(p.event_start) if compiled is not None and not p.events
                   and 0 < p.event_start <= 512 else None)
        try:
            c = curved(position)
            capture = pending
        finally:
            pending = None
        counts["curved_cpu_ns"] += process_time_ns() - start
        counts["prediction_calls"] += 1
        start = process_time_ns()
        use_factor = capture is not None and capture.valid()
        counts["gram_or_check_cpu_ns"] += process_time_ns() - start

        def dense_gram():
            start = process_time_ns()
            g = p.noise_groups[p.keep]
            weights = np.asarray(powers)[g] * c["noise_precision"][g] / p.point_noise[p.keep] ** 2
            u = c["features"][p.keep]
            gram = np.diag(c["coefficient_prior_precision"]) + u.T @ (u * weights[:, None])
            counts["gram_or_check_cpu_ns"] += process_time_ns() - start
            return gram

        gram = None if use_factor else dense_gram()
        geometry = event_position.geometry_features(view, position, 0.)
        features = np.column_stack((geometry["features"], design))
        predicted = view.q * geometry["intercept"] + features @ c["coefficient"]
        raw, noise = values - predicted, sigma * np.sqrt(2)
        prediction = None
        if use_factor:
            start = process_time_ns()
            try:
                prediction = predictive_factor(raw, features, noise, groups, capture, len(p.members))
                if not np.isfinite(prediction["objective"]):
                    prediction = None
            except (ValueError, ArithmeticError, np.linalg.LinAlgError):
                prediction = None
            counts["predictive_kernel_cpu_ns"] += process_time_ns() - start
        if prediction is None:
            if gram is None:
                gram = dense_gram()
            start = process_time_ns()
            counts["dense_calls"] += 1
            prediction = event_position.predictive_residual(raw, features, gram, noise, groups)
            counts["predictive_kernel_cpu_ns"] += process_time_ns() - start
        else:
            counts["factor_calls"] += 1
        return c, prediction, predicted, geometry

    text = getsource(source)
    first, last = "        c = curved(position)\n", '        c["curved_negative_twice_elbo"]'
    begin, end = text.index(first), text.index(last)
    old = text[begin:end].splitlines()
    body = "\n".join("    " + line for line in old)
    text = text[:begin] + """        if in_grid():
            c, prediction, predicted, geometry = grid_prediction(
                p, curved, position, view, powers, values, sigma, groups, design,
            )
        else:
""" + body + "\n" + text[end:]
    namespace = dict(vars(event_position), in_grid=in_grid, grid_prediction=grid_prediction)
    exec(compile(text, source.__code__.co_filename, "exec"), namespace)
    attach = namespace[source.__name__]
    with ExitStack() as stack:
        if compiled is not None:
            stack.enter_context(patch.object(port, "NativeBound", factory))
        # The selected packet constructs its final closures through this port.
        stack.enter_context(patch.object(recovery_inventory, "attach_event_predictive", attach))
        yield counts
