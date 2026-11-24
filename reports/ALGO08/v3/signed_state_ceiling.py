"""Observe exact duplicate inputs in the unchanged signed calibration pair."""

from collections import defaultdict
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from time import process_time_ns
from unittest.mock import patch

import numpy as np


BANK_FIELDS = ("time_s", "position_km", "velocity_km_s")


def exact(value, *, layout=True):
    a = np.asarray(value)
    return a.dtype.str, a.shape, a.strides if layout else (), sha256(a.tobytes()).hexdigest()


class Census:
    def __init__(self, scan):
        self.scan = scan
        self.arm = None
        self.epoch = -1
        self.position = None
        self.views = {}
        self.banks = {}
        self.records = defaultdict(list)
        self.keys = defaultdict(dict)
        self.common = defaultdict(dict)
        self.phase_views = []

    def bank(self, bank):
        fields = tuple(bank[name] for name in BANK_FIELDS)
        identity = tuple(id(field) for field in fields)
        if identity not in self.banks:
            self.banks[identity] = fields, tuple(exact(field) for field in fields)
        return self.banks[identity][1]

    def rows(self, times, labels):
        key = id(times), id(labels)
        if key not in self.views:
            self.views[key] = times, labels, (exact(times), exact(labels))
        return self.views[key][2]

    def sample(self, name, make_key):
        began = process_time_ns()
        identity = make_key()
        seen = self.keys[name]
        arm, epoch = self.arm, self.epoch
        before_lookup = process_time_ns()
        first = seen.setdefault(identity, (arm, epoch, len(self.records[name])))
        after_lookup = process_time_ns()
        row = dict(arm=arm, epoch=epoch, first=first, lookup_cpu_ns=after_lookup - before_lookup,
                   key_cpu_ns=after_lookup - began)
        self.records[name].append(row)
        return row

    def watch(self, name, operation, key):
        def observed(*args, **kwargs):
            row = self.sample(name, lambda: key(*args, **kwargs))
            start = process_time_ns()
            result = operation(*args, **kwargs)
            row["cpu_ns"] = process_time_ns() - start
            return result

        return observed

    def phase_projection(self, problem, point):
        if problem.scan is not self.scan:
            raise ValueError("Unexpected sky or geographic frame in signed geometry")
        return (self.bank(problem.sky), self.bank(problem.mode_bank), self.rows(problem.flat_times, problem.flat_labels),
                exact(problem.reference[problem.flat_labels]), len(problem.reference), exact(point))

    def phase_interpolation(self, bank, times, labels, phases):
        return self.bank(bank), self.rows(times, labels), exact(phases[np.asarray(labels)])

    def prepare(self, bank, modes, times, labels, phases):
        return self.phase_interpolation(bank, times, labels, phases), self.bank(modes), len(phases)

    def frequency(self, bank, times, labels, phases, latitude, longitude, *, altitude_m=0.):
        return self.phase_interpolation(bank, times, labels, phases), coordinate(latitude, longitude, altitude_m)

    def modes(self, bank, modes, times, labels, phases, latitude, longitude, *, altitude_m=0.):
        return self.prepare(bank, modes, times, labels, phases), coordinate(latitude, longitude, altitude_m)

    def bound(self, original):
        observe = self.watch("curved_posterior", original, operands)

        def posterior(raw, features, sigma, groups, *args, **options):
            result = observe(raw, features, sigma, groups, *args, **options)
            if self.epoch == 0 and self.position is not None:
                began = process_time_ns()
                if self.arm == "fitted_c":
                    features = np.delete(features, 8, axis=1)
                self.common[self.arm][self.position] = dict(
                    response=exact(raw, layout=False), common_design=exact(features, layout=False),
                    point_sigma=exact(sigma, layout=False), groups=exact(groups, layout=False),
                    powers=exact(options.get("powers"), layout=False) if "powers" in options else None,
                    final_noise_precision=exact(result["noise_precision"], layout=False))
                self.records["curved_posterior"][-1]["common_key_cpu_ns"] = process_time_ns() - began
            return result

        return posterior

    def validate(self):
        if any(exact(values) != pin for fields, pins in self.banks.values() for values, pin in zip(fields, pins, strict=True)):
            raise ValueError("The orbit inputs were modified in place")
        if any((exact(times), exact(labels)) != check for times, labels, check in self.views.values()):
            raise ValueError("The geometry row inputs were modified in place")

    def scopes(self):
        return {name: summarize(records) for name, records in self.records.items()}

    def compare_common(self):
        left, right = self.common["c0"], self.common["fitted_c"]
        common = left.keys() & right.keys()
        return dict(common_coordinate_count=len(common), fields_equal={field: sum(left[key][field] == right[key][field]
                  for key in common) for field in next(iter(left.values()))} if left else {})


def coordinate(*values):
    return np.asarray(values, dtype=np.float64).tobytes()


def operands(*args, **kwargs):
    return (tuple(None if item is None else exact(item) for item in args),
            tuple((key, None if value is None else exact(value)) for key, value in sorted(kwargs.items())))


def summarize(rows):
    totals = dict(calls=len(rows), cpu_ns=0, key_cpu_ns=0, lookup_cpu_ns=0, extra_common_key_cpu_ns=0)
    for index, row in enumerate(rows):
        cpu = row.get("cpu_ns", 0)
        totals["cpu_ns"] += cpu
        totals["key_cpu_ns"] += row["key_cpu_ns"]
        totals["lookup_cpu_ns"] += row["lookup_cpu_ns"]
        totals["extra_common_key_cpu_ns"] += row.get("common_key_cpu_ns", 0)
        arm, epoch, previous = row["first"]
        if previous == index:
            continue
        scope = ("across_arms" if row["arm"] != arm else "later_refresh" if row["epoch"] != epoch
                 else "same_refresh")
        duplicate = totals.setdefault(scope, dict(calls=0, cpu_ns=0))
        duplicate["calls"] += 1
        duplicate["cpu_ns"] += cpu
    return totals


@contextmanager
def observe(census):
    from leo.analysis.localization_v3 import event_position as event, marginal, predictive_linear as linear
    from leo.analysis.research import continuous_curve_fit as frequency, orbit_uncertainty as modes

    if event.geometry_features is not linear.geometry_features:
        raise ValueError("The original predictive geometry binding is not active")

    original_cached, original_make, original_fit = event.cached, event.make_event_problem, event.fit

    def make(scan, node, keep, arm, reference, *args, **kwargs):
        if scan is not census.scan:
            raise ValueError("Unexpected scan in the original production pair")
        census.epoch = census.epoch + 1 if census.arm == arm else 0
        census.arm = arm
        view = original_make(scan, node, keep, arm, reference, *args, **kwargs)
        census.phase_views.append(dict(arm=arm, epoch=census.epoch, reference=exact(reference),
                                       members=tuple(view.members), aliases=tuple(view.alias),
                                       keep=exact(view.keep), phase_width=exact(view.phase_sigma)))
        return view

    def cache(p):
        actual = p.calculate

        def evaluate(x):
            point = coordinate(*x)
            old = census.position
            census.position = point
            try:
                return actual(x)
            finally:
                census.position = old

        p.calculate = census.watch("paid_full_objective", evaluate,
                                   lambda x: (census.arm, exact(p.reference), coordinate(*x)))
        return original_cached(p)

    def fit(p, *args, **kwargs):
        residual = p.residual
        begin = len(census.records["optimizer_requests"])

        def requested(x):
            census.sample("optimizer_requests", lambda: (census.arm, census.epoch, coordinate(*x)))
            return residual(x)

        try:
            p.residual = requested
            result = original_fit(p, *args, **kwargs)
        finally:
            p.residual = residual
        if result["evaluations"] != len(census.records["optimizer_requests"]) - begin:
            raise ValueError("Optimizer request count did not match the actual fit")
        return result

    def frame(operation, key):
        return census.watch(key, operation, coordinate)

    with ExitStack() as stack:
        ports = ((event, "make_event_problem", make), (event, "cached", cache), (event, "fit", fit),
                 (marginal, "_phase_geometry", census.watch("curved_phase_projection", marginal._phase_geometry, census.phase_projection)),
                 (marginal, "prepare_phase_geometry", census.watch("curved_nominal_and_modes_interpolation", marginal.prepare_phase_geometry, census.prepare)),
                 (marginal, "paired_phase_states", census.watch("curved_derivative_interpolation", marginal.paired_phase_states, census.phase_interpolation)),
                 (linear, "paired_phase_frequency", census.watch("predictive_phase_frequency", linear.paired_phase_frequency, census.frequency)),
                 (linear, "paired_frequency_modes", census.watch("predictive_frequency_modes", linear.paired_frequency_modes, census.modes)),
                 (event, "predictive_residual", census.watch("predictive_covariance", event.predictive_residual, operands)),
                 (frequency, "geodetic_to_ecef_km", frame(frequency.geodetic_to_ecef_km, "receiver_ecef")),
                 (modes, "geodetic_to_ecef_km", frame(modes.geodetic_to_ecef_km, "receiver_ecef")),
                 (frequency, "ecef_to_enu_matrix", frame(frequency.ecef_to_enu_matrix, "receiver_enu")),
                 (census.scan, "bound", census.bound(census.scan.bound)))
        for owner, name, replacement in ports:
            stack.enter_context(patch.object(owner, name, replacement))
        yield event
