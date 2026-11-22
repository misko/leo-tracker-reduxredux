"""Reuse exact nominal perturbation states while preserving prior-specific mode scales."""

from collections import Counter, OrderedDict
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from inspect import getsource
from time import process_time_ns
from unittest.mock import patch

from sgp4.api import accelerated

from leo.analysis.localization_v3 import orbit_modes


SOURCE_SHA256 = "58195aedd0e7bf49bafe4e812f98f5ea05140fc49ffde5c6961717963301fe59"
MAX_BYTES = 8 * 1024**2


def nominal_key(scan, label):
    number = int(scan.norads[label])
    knots = scan.sky["time_s"]
    return (scan.origin_utc_ns, number, tuple(scan.elements[str(number)]["lines"]),
            knots.dtype.str, knots.shape, knots.tobytes())


def propagate_angles(scan, label, satellite):
    satellites = tuple(orbit_modes.perturb(satellite, axis, delta)
                       for axis in ("inclination_deg", "raan_deg") for delta in (.001, -.001))
    number = int(scan.norads[label])
    catalogue = orbit_modes.ElementSetCatalogue((str(number),) * 4, (number,) * 4, satellites)
    return orbit_modes.ecef_states(catalogue, scan.origin_utc_ns, scan.sky["time_s"])


class AngularBank:
    def __init__(self, enabled, limit=MAX_BYTES):
        self.enabled = enabled and accelerated
        self.limit = limit
        self.size = 0
        self.cache = OrderedDict()
        self.priors = {}
        self.counts = Counter()

    def __call__(self, scan, label, satellite):
        key = nominal_key(scan, label)
        prior = scan.previous_tle_sha256
        self.counts["calls"] += 1
        saved = self.cache.get(key)
        if saved is not None:
            self.cache.move_to_end(key)
            self.counts["hits"] += 1
            self.counts["other_prior_hits"] += int(saved[2] != prior)
            return saved[0]
        duplicate = key in self.priors
        self.counts["repeated_inputs"] += int(duplicate)
        previous = self.priors.setdefault(key, prior)
        self.counts["other_prior_repeats"] += int(previous != prior)
        start = process_time_ns()
        state = propagate_angles(scan, label, satellite)
        spent = process_time_ns() - start
        self.counts["propagation_cpu_ns"] += spent
        self.counts["duplicate_propagation_cpu_ns"] += spent * int(duplicate)
        size = sum(array.nbytes for array in state)
        if self.enabled and size <= self.limit and state[2].all():
            while self.size + size > self.limit:
                _, discarded = self.cache.popitem(last=False)
                self.size -= discarded[1]
            for array in state:
                array.setflags(write=False)
            self.cache[key] = state, size, prior
            self.size += size
        return state


@contextmanager
def nominal_angular_bank(*, enabled):
    from leo.analysis.localization_v3 import family_cavity, history_position, marginal, new_family, prediction

    stock = orbit_modes.build_modes
    source = getsource(stock)
    if sha256(source.encode()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Expected the reviewed stock orbital mode implementation")
    start = source.index("        satellites = tuple(")
    stop = source.index("        if not good.all():", start)
    source = source[:start] + "        p, v, good = angular_states(scan, j, sat)\n" + source[stop:]
    bank = AngularBank(enabled)
    scope = dict(vars(orbit_modes), angular_states=bank)
    exec(compile(source, stock.__code__.co_filename, "exec"), scope)
    operation = scope[stock.__name__]
    with ExitStack() as stack:
        for module in (orbit_modes, marginal, history_position, family_cavity, new_family, prediction):
            if module.build_modes is stock:
                stack.enter_context(patch.object(module, "build_modes", operation))
        yield bank.counts
