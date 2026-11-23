"""Exact retained setup and fixed-phase reuse within the original signed fit."""

import ast
from collections import Counter, OrderedDict
from contextlib import ExitStack, contextmanager
from copy import copy
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from time import process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np


HISTORY_SHA = "00e349de1a25ac62fb287f970a005737675b5f2e6d45273baa9c914e8a7918f0"
CAPACITY = 64
STATIC_PREDICTION = ("flat_times", "flat_labels", "q", "hardware", "smooth", "constants")


def point_key(point):
    value = np.asarray(point)
    return value.dtype.str, value.shape, value.tobytes()


class Setup:
    """One arm's fixed roster, noise, columns and powered normalizer."""

    def __init__(self, original, counters):
        self.original = original
        self.counters = counters
        self.template = self.source = self.curved = self.linear = None

    def problem(self, scan, node, arm, keep, reference):
        if self.template is None:
            self.source = scan, node, arm, keep
            self.template = self.original(scan, node, arm, keep, reference)
            self.counters["base_builds"] += 1
        else:
            scan0, node0, arm0, keep0 = self.source
            if scan is not scan0 or node is not node0 or arm != arm0 or keep is not keep0:
                raise ValueError("Expected one invariant signed roster and calibration arm")
            self.counters["base_reuses"] += 1
        result = copy(self.template)
        result.reference = np.asarray(reference)
        result.phase_sigma = self.template.phase_sigma.copy()
        return result

    def retained(self, p, keep, weights, width):
        if self.curved is None:
            selected = p.noise_groups[keep]
            noise = p.point_noise[keep]
            present = np.unique(selected)
            scale = np.ones(width)
            scale[-len(p.members):] = 0.3
            volume = float(2 * np.sum(weights[selected] * np.log(noise / 40)))
            self.curved = present, scale, noise, selected, weights[present], volume
            self.counters["retained_builds"] += 1
        else:
            self.counters["retained_reuses"] += 1
        return self.curved

    def predictive(self, original, p, entries):
        if self.linear is None:
            view, *tail = original(p, entries)
            self.linear = entries, {field: getattr(view, field) for field in STATIC_PREDICTION}, tail
            self.counters["predictive_layout_builds"] += 1
            return view, *tail
        prior_entries, fixed, tail = self.linear
        if entries is not prior_entries:
            raise ValueError("Expected the same selected predictive entries for all refreshes")
        self.counters["predictive_layout_reuses"] += 1
        return SimpleNamespace(**(vars(p) | fixed)), *tail


def retained_factory(original, source, setup):
    """Preserve the shipped selected-design kernel and arithmetic order."""
    node, = (item for item in ast.parse(source).body if isinstance(item, ast.FunctionDef)
             and item.name == "make_problem")
    code = ast.get_source_segment(source, node)
    replacements = {
        "    def calculate(x):": "    present, scale, noise, selected, selected_powers, volume = _retained(p, keep, weights, width)\n\n    def calculate(x):",
        "        scale = np.ones(width)\n        scale[-len(p.members) :] = 0.3\n": "",
        "        present = np.unique(p.noise_groups[keep])\n": "",
        "(features * scale)[keep]": "_select(features, scale, keep)",
        "            p.point_noise[keep],\n            p.noise_groups[keep],\n            powers=weights[present],":
            "            noise,\n            selected,\n            powers=selected_powers,",
        "        volume = float(2 * np.sum(weights[p.noise_groups[keep]] * np.log(p.point_noise[keep] / 40)))\n": "",
    }
    for before, after in replacements.items():
        if code.count(before) != 1:
            raise ValueError("Expected the original retained-likelihood arithmetic")
        code = code.replace(before, after)
    if not callable(original.__globals__.get("_select")):
        raise ValueError("Expected the installed direct selected-design binding")
    scope = dict(original.__globals__, problem=setup.problem, _retained=setup.retained)
    exec(compile(code, original.__code__.co_filename, "exec"), scope)
    return scope["make_problem"]


def memo_residual(operation, counters):
    """The optimizer consumes read-only vectors, one cache per actual phase view."""
    released = OrderedDict()

    @lru_cache(maxsize=CAPACITY)
    def evaluate(key):
        dtype, shape, data = key
        result = operation(np.frombuffer(data, dtype=dtype).reshape(shape))
        counters["residual_bytes"] = max(counters["residual_bytes"], result.nbytes)
        return result

    def residual(x):
        counters["residual_requests"] += 1
        original_key = tuple(x)
        if original_key in released:
            counters["released_recent_hits"] += 1
            released.move_to_end(original_key)
        else:
            released[original_key] = None
            if len(released) > 8:
                released.popitem(last=False)
        return evaluate(point_key(x))

    residual.cache_info = evaluate.cache_info
    residual.cache_clear = evaluate.cache_clear
    return residual


def timed(operation, counters, key):
    def call(*args, **kwargs):
        start = process_time_ns()
        try:
            return operation(*args, **kwargs)
        finally:
            counters[key + "_calls"] += 1
            counters[key + "_cpu_ns"] += process_time_ns() - start
    return call


@contextmanager
def arm_reuse(scan, counters, epochs, ports):
    event, original_predictive, prepared, _modules = ports
    history = Path(event.make_problem.__code__.co_filename).read_bytes()
    if sha256(history).hexdigest() != HISTORY_SHA:
        raise ValueError("Unexpected released history likelihood")
    make = event.make_event_problem
    attach, start_cache, fit, linear = event.attach_event_predictive, event.cached, event.fit, event.linear_geometry
    setup = Setup(event.make_problem.__globals__["problem"], counters)
    optimized_factory = retained_factory(event.make_problem, history.decode(), setup)
    view_seen, prepared_valid = None, False

    def make_problem(*args, **kwargs):
        counters["refreshes"] += 1
        return make(*args, **kwargs, base_problem_factory=optimized_factory)

    def attached(p, entries, powers):
        original = timed(p.calculate, counters, "curved")
        latest = None

        def curved(x):
            nonlocal latest
            result = original(x)
            # The released predictive wrapper assigns new dictionary fields and
            # replaces scalar/array values without writing the shared input arrays.
            latest = point_key(x), dict(result)
            return result

        def curved_summary(x):
            result = p.calculate(x)
            if "_signed_reuse_curved" in result:
                counters["summary_curved_hits"] += 1
                return result["_signed_reuse_curved"]
            counters["summary_curved_misses"] += 1
            return original(x)

        p.calculate = curved
        result = attach(p, entries, powers)
        if entries:
            attached_calculation = p.calculate

            def calculate(x):
                fitted = attached_calculation(x)
                if latest is not None and point_key(x) == latest[0]:
                    fitted["_signed_reuse_curved"] = latest[1]
                return fitted

            p.calculate = calculate
            p.curved_calculate = curved_summary
        return result

    ordinary_geometry = timed(original_predictive, counters, "ordinary_geometry")
    prepared_geometry = timed(prepared, counters, "prepared_geometry")

    def predictive_geometry(view, position, altitude_m):
        from grid_phase_state_reuse import identical

        nonlocal view_seen, prepared_valid
        if view is not view_seen:
            view_seen = view
            before = ordinary_geometry(view, position, altitude_m)
            candidate = prepared_geometry(view, position, altitude_m)
            prepared_valid = identical(before, candidate)
            counters["geometry_verified" if prepared_valid else "geometry_fallbacks"] += 1
            return candidate if prepared_valid else before
        return (prepared_geometry if prepared_valid else ordinary_geometry)(view, position, altitude_m)

    def cache(p):
        uncached = timed(p.calculate, counters, "full_evaluation")
        p.calculate = uncached
        start_cache(p)
        p.residual = memo_residual(p.residual, counters)
        return p

    def fitted(p, x, **kwargs):
        result = fit(p, x, **kwargs)
        info = p.residual.cache_info()
        epochs.append(dict(phase_sha256=sha256(point_key(p.reference)[2]).hexdigest(), cache=info._asdict()))
        p.residual.cache_clear()
        return result

    with ExitStack() as stack:
        for name, value in (("make_event_problem", timed(make_problem, counters, "retained_setup")),
                            ("attach_event_predictive", timed(attached, counters, "predictive_setup")),
                            ("linear_geometry", lambda p, entries: setup.predictive(linear, p, entries)),
                            ("geometry_features", predictive_geometry), ("cached", cache), ("fit", fitted),
                            ("predictive_residual", timed(event.predictive_residual, counters, "predictive_covariance"))):
            stack.enter_context(patch.object(event, name, value))
        stack.enter_context(patch.object(scan, "bound", timed(scan.bound, counters, "bound")))
        yield


def isolated_pair(candidate, means):
    from grid_phase_state_reuse import checked_geometry
    from named_survivor_fit import ARMS, clock, fit_record, now

    ports = checked_geometry()
    event = ports[0]
    scan, node, keep, powers, model, entries = (candidate[k] for k in ("scan", "node", "keep", "powers", "model", "entries"))
    records, audit = {}, {}
    for arm in ARMS:
        began, counts, epochs = now(), Counter(), []
        with arm_reuse(scan, counts, epochs, ports):
            records[arm] = event.refit(scan, node, keep, arm, powers, means, model, [], entries)
        clocks = clock(began)
        audit[arm] = dict(timing=clocks, counts=dict(counts), epochs=epochs, fit=fit_record(records[arm]))
    return records, audit
