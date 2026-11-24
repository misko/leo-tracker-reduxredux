"""Opt-in post-propagation laziness for the original confidence width consumer."""

from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from unittest.mock import patch

import numpy as np

from accepted_confidence_trace import PIN as CONFIDENCE_PIN, fingerprint


RETAINED_PIN = "5d491104a62a78f177a556366168767c5fd62b0dca41c9cf168fe2597f40a81e"
ORBIT_PIN = "778104949ad9467b613ffab820a75db013b33fa86ad810ea00b226841fdc8b52"
SHIFT_PIN = "8affea2a053f3acd2edf38d7daaa2cfe7fcdc86293261fbff69e9e14a0df4d56"
PARSE = "    old = parse_element_sets(scan.previous_tle)"
MATERIALIZE = "    pp, vv = phase_shifted_states("
LAZY_PARSE = """    cached = cached_widths(scan, key)
    if cached is not None:
        return cached
    old = parse_element_sets(scan.previous_tle)"""
LAZY_MATERIALIZE = """    only_widths = aligned_widths(numbers, phase, knots, current["time_s"], po, vo)
    if only_widths is not None:
        return only_widths
    pp, vv = phase_shifted_states("""


def require_source(module, pin):
    path = Path(module.__file__)
    if sha256(path.read_bytes()).hexdigest() != pin:
        raise ValueError(f"Unexpected confidence width source {path}")


class WidthAlignments:
    def __init__(self, shifted, audit):
        self.shifted = shifted
        self.audit = audit
        self.owner = None
        self.key = None
        self.result = None

    def version(self, scan, labels):
        # The scan owns writable arrays. Exact bytes detect any in-place changes
        # before a cached prior is admissible under this research binding.
        return fingerprint(scan.origin_utc_ns, scan.previous_tle_sha256, scan.norads,
                           *(scan.sky[name] for name in ("time_s", "position_km", "velocity_km_s")), labels)

    def cached(self, scan, labels):
        key = self.version(scan, labels)
        if self.owner is scan and self.key == key and self.result is not None:
            self.audit["width_alignment_hits"] += 1
            return self.result
        self.owner, self.key, self.result = scan, key, None
        return None

    def aligned(self, numbers, phase, knots, times, position, velocity):
        # Validation of all emitted earlier SGP4/ECEF knots still runs. The exact
        # shift routine validates the bank and both extreme queries. Interior
        # queries are monotone between those extrema for each labelled satellite.
        # A conservative binary64 bound guarantees the omitted interpolation and
        # rotation stay finite, including sums of products. Nonstandard FP
        # warning/exception modes use the original full materialization.
        bound = np.finfo(np.float64).max / 16
        if (np.geterr()["under"] != "ignore"
                or not all(isinstance(a, np.ndarray) and a.dtype == np.float64 and a.size
                           and -bound <= a.min() <= a.max() <= bound for a in (position, velocity))):
            self.audit["ordinary_materialization"] += 1
            return None
        previous = dict(time_s=knots, position_km=position, velocity_km_s=velocity)
        self.shifted(previous, times[[0, -1]], -phase)
        self.audit["padded_health_checked"] += 1
        self.audit["alignment_labels"] += len(numbers)
        self.audit["padded_propagation_cells"] += len(numbers)*len(knots)
        self.audit["interior_shift_cells_elided"] += len(numbers)*(len(times)-2)
        self.result = None, None, dict(zip(numbers, map(float, phase), strict=True))
        return self.result


@contextmanager
def binding(estimator, audit):
    """Set up before the installed named-history wrapper enters the solver."""
    from leo.analysis.localization_v3 import orbit_modes as modes, retained_position as retained
    from leo.analysis.research import orbit_phase_geometry as shift

    for module, pin in ((estimator, CONFIDENCE_PIN), (modes, ORBIT_PIN), (retained, RETAINED_PIN), (shift, SHIFT_PIN)):
        require_source(module, pin)
    original = estimator.phase_widths
    if (original is not retained.phase_widths or retained.previous_bank is not modes.previous_bank
            or modes.previous_bank.__code__.co_filename != modes.__file__
            or modes.phase_shifted_states is not shift.phase_shifted_states):
        raise ValueError("Expected the original width and phase-shift callbacks before binding")
    source = getsource(modes.previous_bank)
    if source.count(PARSE) != 1 or source.count(MATERIALIZE) != 1:
        raise ValueError("Expected one original padded earlier-bank materialization")
    bank = compile(source.replace(PARSE, LAZY_PARSE).replace(MATERIALIZE, LAZY_MATERIALIZE), modes.__file__, "exec")
    width = compile(getsource(original), retained.__file__, "exec")
    memo = WidthAlignments(shift.phase_shifted_states, audit)

    def observed(scan, labels):
        if (not isinstance(labels, list) or len(labels) != len(scan.norads)
                or any(j != i for i, j in enumerate(labels))
                or modes.phase_shifted_states is not memo.shifted
                or np.geterr()["under"] != "ignore"):
            return original(scan, labels)
        namespace = dict(vars(modes), cached_widths=memo.cached, aligned_widths=memo.aligned)
        exec(bank, namespace)
        consumer = dict(vars(retained), previous_bank=namespace["previous_bank"])
        exec(width, consumer)
        try:
            return consumer["phase_widths"](scan, labels)
        except (AssertionError, ValueError, FloatingPointError):
            # Recover through the currently installed original history wrapper.
            # In particular its original three-sample assertion has a named
            # recovery; a padded-grid failure still propagates as before.
            audit["original_replay_after_guard_error"] += 1
            return original(scan, labels)

    with patch.object(estimator, "phase_widths", observed):
        yield
