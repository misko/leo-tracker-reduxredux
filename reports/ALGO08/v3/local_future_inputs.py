"""Original receiver opportunities for the bounded local repair."""

from causal_short_receiver import identity
from full_short_raw import RECIPE_SHA


MAX_GAP_S = 8.


def directions(probes):
    from tools.pipeline_eval.variants.carrier_continuation import Continuation

    history = Continuation()
    past = []
    for row in probes:
        if len(row["candidates"]) > 1:
            raise ValueError("Expected the single-factor signed short receiver")
        past.append(history.select(row)[1] is not None)
    history = Continuation()
    future = [history.select(dict(row, valid_start_counter=-row["valid_start_counter"]))[1] is not None
              for row in reversed(probes)][::-1]
    return past, future


def selection(native):
    from leo.analysis.localization_v3.tracks import winning_observations
    from north_factor_swap import rebound

    if native["provenance"]["detector_sha256"] != "sha256:" + RECIPE_SHA:
        raise ValueError("Local repair requires the original unfiltered full-short detector")
    recipe, _ = identity(RECIPE_SHA)
    original = native["source"]["probes"]
    past, reverse = directions(original)
    forward_probes, missing = [], []
    for row, earlier, later in zip(original, past, reverse, strict=True):
        empty = dict(row, candidates=[])
        forward_probes.append(row if earlier else empty)
        missing.append(row if later and not earlier else empty)
    forward = rebound(native, forward_probes, recipe)
    count = sum(later and not earlier for earlier, later in zip(past, reverse, strict=True))
    rows, _ = winning_observations(dict(native, source=dict(native["source"], probes=missing))) if count else ([], None)
    if len(rows) != count:
        raise ValueError("The unseen future-supported factors differ from the locked two-sided rule")
    return forward, rows


def future_observations(native, forward):
    projected, rows = selection(native)
    if forward != projected:
        raise ValueError("The original forward continuation differs from the shared selector")
    return rows


def lane(row):
    return row["receiver"], row["channel"], row["actual_rf_hz"]
