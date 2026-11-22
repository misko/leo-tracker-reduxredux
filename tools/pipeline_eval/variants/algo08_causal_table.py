"""Share immutable TLE representations across the original causal policies."""

from contextlib import ExitStack, contextmanager
from functools import lru_cache, wraps
from time import process_time
from unittest.mock import patch

from sgp4.api import accelerated


def timed(operation, counters, name):
    @wraps(operation)
    def measure(*args, **kwargs):
        start = process_time()
        try:
            return operation(*args, **kwargs)
        finally:
            counters[name + "_calls"] = counters.get(name + "_calls", 0) + 1
            counters[name + "_cpu_s"] = counters.get(name + "_cpu_s", 0.) + process_time() - start

    return measure


def release_after(operation, release):
    @wraps(operation)
    def wrapped(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        finally:
            release()

    return wrapped


@contextmanager
def causal_table(*, canonical_exports=False, previous_catalogues=False):
    """Retain canonical lines by parsed record identity and prior text by exact bytes."""
    from leo.analysis.localization_v3 import orbit_modes
    from leo.application import localization_v3 as application
    from leo.operations import localization_v3_inputs as inputs

    counts, caches = {}, {}

    def drain(name):
        operation = caches[name]
        info = operation.cache_info()
        hits, peak = name + "_hits", name + "_retained_peak"
        counts[hits] = counts.get(hits, 0) + info.hits
        counts[peak] = max(counts.get(peak, 0), info.currsize)
        operation.cache_clear()

    # The accelerated SatrecArray copies its input records for propagation.
    # Preserve the stock lifetime of mutable scalar fallback SGP4 objects.
    routes = (
        (inputs, "export_tle", "canonical_export", canonical_exports, 65_536),
        (orbit_modes, "parse_element_sets", "distinct_previous_parse", previous_catalogues, 4),
        (application, "prepare_initial_sky", "initial_sky", False, 0),
        (application, "prepare_phase_history", "phase_history", False, 0),
        (application, "forecast", "forecast", False, 0),
    )
    with ExitStack() as stack:
        for module, attr, name, cache, budget in routes:
            operation = timed(getattr(module, attr), counts, name)
            if accelerated and cache:
                operation = lru_cache(maxsize=budget)(operation)
                caches[name] = operation
            if name == "phase_history" and "canonical_export" in caches:
                operation = release_after(operation, lambda: drain("canonical_export"))
            stack.enter_context(patch.object(module, attr, operation))
        try:
            yield counts
        finally:
            for name in caches:
                drain(name)
