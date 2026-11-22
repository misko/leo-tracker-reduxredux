"""Reject fine salvage supports only when no original phase can be admitted."""

from collections import Counter
from contextlib import contextmanager
from inspect import getsource
from time import process_time
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import v5_tiled_salvage


def upper(value):
    return np.nextafter(value, np.inf)


def raw_error_limit(noise):
    """An outward-rounded limit on raw + alias - bias if the stock gates pass."""
    # The division's exact result lies below the successor of its rounded
    # result. Restore both addition roundoffs from the bounded outputs.
    residual = upper(noise * upper(6.))
    alias_minus_bias = upper(residual)
    aliased = upper(alias_minus_bias + 3000.)
    return upper(alias_minus_bias + (upper(aliased) - aliased))


class EndpointWitness:
    def __init__(self, raw, elevation, limit):
        self.raw, self.elevation, self.limit = raw, elevation, limit

    @classmethod
    def prepare(cls, y, noise, frequency, elevation, rf, times):
        # Stay well inside finite binary64 for all stock weighted squares and
        # reductions. These limits are on arithmetic, not signal eligibility.
        maximum = 2. ** 100
        if (
            len(y) >= 2 ** 20 or not np.isfinite(rf) or abs(rf) > maximum
            or not all(a.dtype == np.float64 for a in (y, noise, frequency, elevation, times))
            or not all(np.isfinite(a).all() for a in (y, noise, frequency, elevation, times))
            or np.max(np.abs(y), initial=0.) > maximum
            or np.max(np.abs(frequency), initial=0.) > maximum
            or np.max(np.abs(times), initial=0.) > maximum
            or np.any(noise < 1. / maximum) or np.any(noise > maximum)
        ):
            return None
        raw = y - rf * frequency
        return cls(raw, elevation, raw_error_limit(noise))

    def rejects(self, start, stop):
        last = stop - 1
        difference = np.nextafter(np.abs(self.raw[:, start] - self.raw[:, last]), -np.inf)
        limit = upper(self.limit[start] + self.limit[last])
        invisible_at_endpoint = (self.elevation[:, start] < 0) | (self.elevation[:, last] < 0)
        return bool(np.all(invisible_at_endpoint | (difference > limit)))


def defer_noise(residual, times, rms, bias, cost, maximum):
    """Only bypass the expensive gate after a cheap original gate has failed."""
    return (
        (rms > 450 or abs(bias) > 3000 or not np.isfinite(cost) or maximum > 6)
        and len(residual) >= 4 and len(times) == len(residual)
        and np.isfinite(residual).all() and np.isfinite(times).all() and np.ptp(times) > 0
    )


def instrument(original, mode, metrics):
    """Scope the experiment to the exact original support and ranking loop."""
    source = getsource(original)
    edits = (
        (
            "        for a, b in supports:\n            terms = kernel.profile",
            """        witness = EndpointWitness.prepare(y, noise, f, e, rf, t) if use_bound else None
        for a, b in supports:
            metrics["support_trials"] += 1
            if witness is not None and witness.rejects(a, b):
                metrics["rejected_by_bound"] += 1
                continue
            metrics["profile_calls"] += 1
            terms = kernel.profile""",
        ),
        (
            "            screen = kernel.batch_noise_screen(residual[None], t[a:b])\n"
            "            max_sigma = np.max(abs(residual) / noise[a:b])\n",
            """            if use_gate:
                max_sigma = np.max(abs(residual) / noise[a:b])
                if defer_noise(residual, t[a:b], terms["rms"][best], terms["bias"][best],
                               cost[best], max_sigma):
                    metrics["rejected_before_noise"] += 1
                    continue
            metrics["noise_calls"] += 1
            screen = kernel.batch_noise_screen(residual[None], t[a:b])
            if not use_gate:
                max_sigma = np.max(abs(residual) / noise[a:b])
""",
        ),
    )
    for before, after in edits:
        if source.count(before) != 1:
            raise ValueError("Unexpected fine salvage gates or support loop")
        source = source.replace(before, after)
    namespace = dict(np=np, EndpointWitness=EndpointWitness, defer_noise=defer_noise,
                     use_bound=mode == "bound", use_gate=mode != "control", metrics=metrics)
    exec(compile(source, original.__code__.co_filename, "exec"), namespace)
    return namespace[original.__name__]


@contextmanager
def stable_pruning(mode):
    metrics = Counter()
    original = v5_tiled_salvage.fine_alternatives
    revised = instrument(original, mode, metrics)

    def measured(*args, **kwargs):
        start = process_time()
        try:
            return revised(*args, **kwargs)
        finally:
            metrics["fine_cpu_s"] += process_time() - start

    with patch.object(v5_tiled_salvage, "fine_alternatives", measured):
        yield metrics
