"""Reuse exact work inside one held-family calculation in installed named inference."""

from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from struct import pack
from unittest.mock import patch

import numpy as np


PINS = {
    "family_cavity": "7a20ac84d4c245df95481d10425def01642cbf4d3f45f1f32b9188a78007b3ae",
    "cavity_prediction": "be422d23c3a547dcb964987155276440dee82babe32a21afd84570c13a0e3e19",
    "marginal": "c80ac51249578e8a2c6c6a13a04aaa22a168353b2c758155858106b91507b609",
}


def exact_source(operation, replacements, **helpers):
    source = getsource(operation)
    for old, new in replacements:
        if source.count(old) != 1:
            raise ValueError(f"Unexpected installed held-family boundary: {operation.__name__}")
        source = source.replace(old, new)
    environment = dict(operation.__globals__, **helpers)
    exec(compile(source, operation.__code__.co_filename, "exec"), environment)
    return environment[operation.__name__]


def state_readout(problem, point, counters):
    """Save exactly the calculation consumed by the ordinary final state read."""
    ordinary = problem.calculate
    key = np.asarray(point, np.float64).tobytes()
    saved = None

    def capture(x):
        nonlocal saved
        result = ordinary(x)
        if np.asarray(x, np.float64).tobytes() == key:
            saved = result
        return result

    with patch.object(problem, "calculate", capture):
        state = problem.state(point)
    if saved is None:
        counters["ordinary_endpoint"] += 1
        saved = ordinary(point)
    else:
        counters["saved_native_endpoint"] += 1
    return state, saved


class FixedPhase:
    """Reuse results only on the same finite phase and immutable candidate data."""

    def __init__(self, counters):
        self.counts = counters
        self.phase = self.result = self.geometry_result = self.root = None

    def prior_root(self, covariance):
        if self.root is None:
            self.root = np.linalg.cholesky(covariance)
            self.counts["prior_factorizations"] += 1
        else:
            self.counts["reused_prior_factorizations"] += 1
        return self.root

    def evaluate(self, phase, geometry, values, mean, predict):
        key = pack("=d", phase)
        if key != self.phase:
            self.geometry_result = geometry(phase)
            intercept, design, _ = self.geometry_result
            self.result = predict(values - intercept - design @ mean, design)
            self.phase = key
            self.counts["dynamic_predictions"] += 1
        else:
            self.counts["reused_predictions"] += 1
        return *self.geometry_result, self.result

    def final_geometry(self, phase, geometry):
        if pack("=d", phase) == self.phase:
            self.counts["reused_final_geometry"] += 1
            return self.geometry_result
        return geometry(phase)


@contextmanager
def binding():
    """Scope the checked research adapter to one ordinary serial nomination."""
    from leo.analysis.localization_v3 import cavity_prediction, family_cavity, marginal

    counters = Counter()
    ports = family_cavity, cavity_prediction, marginal
    if (any(sha256(Path(mod.__file__).read_bytes()).hexdigest() != PINS[mod.__name__.rsplit(".", 1)[-1]]
            for mod in ports) or family_cavity.gaussian_prediction is not cavity_prediction.gaussian_prediction):
        counters["unsupported"] += 1
        yield counters
        return
    ordinary_family = family_cavity.family_data
    ordinary_predict = family_cavity.candidate_prediction
    family = exact_source(ordinary_family, (
        ('        phase = np.clip(p.state(d["x"])["phases"][p.labels], -15, 15)', '''        if _ == 4:
            state, last = _read(p, d["x"], _counts)
        else:
            state = p.state(d["x"])
        phase = np.clip(state["phases"][p.labels], -15, 15)'''),
        ('    c = p.calculate(d["x"])', '    c = last'),
    ), _read=state_readout, _counts=counters)
    gaussian = exact_source(cavity_prediction.gaussian_prediction, (
        ('def gaussian_prediction(raw, design, covariance, sigma):',
         'def gaussian_prediction(raw, design, covariance, sigma, *, fixed):'),
        ('    root = np.linalg.cholesky(c)', '    root = fixed.prior_root(c)'),
    ))
    prediction = exact_source(ordinary_predict, (
        ('    history = []', '    history = []\n    fixed = _fixed(_counts)'),
        ('''        intercept, features, e = geometry(reference)
        result = gaussian_prediction(
            values - intercept - features @ mean, features, covariance, data["noise"]
        )''', '''        intercept, features, e, result = fixed.evaluate(
            reference, geometry, values, mean,
            lambda raw, design: _predict(raw, design, covariance, data["noise"], fixed=fixed),
        )'''),
        ('        intercept, features, e = geometry(phase)',
         '        intercept, features, e = fixed.final_geometry(phase, geometry)'),
    ), _fixed=FixedPhase, _predict=gaussian, _counts=counters)
    with (patch.object(family_cavity, "family_data", family),
          patch.object(family_cavity, "candidate_prediction", prediction)):
        yield counters
