"""Score joint carrier and arrival proposals on the receiver's original empty short lanes."""

from math import isfinite, remainder

from .directed_donor import ADC, PERIOD, arrival_phase


WINDOWS = {"primary": (250., 2.), "historical_tight": (400., 1.), "historical_loose": (2250., 6.),
           "wider_timing": (250., 128.)}
PHASES = ("interpolated", "left_only", "quarter_period_control")


def phases(left, target_counter, right):
    """Interpolate physical arrival phase without converting large counters into floats."""
    start, stop = left["counter"], right["counter"]
    if not start < target_counter < stop:
        raise ValueError("The candidate neighbors must strictly bracket the target in hardware time")
    a = arrival_phase(start, left["factor"])
    b = arrival_phase(stop, right["factor"])
    if not isfinite(a) or not isfinite(b):
        raise ValueError("Expected finite observed frame epochs")
    fraction = (target_counter-start)/(stop-start)
    predicted = (a + fraction * remainder(b-a, PERIOD)) % PERIOD
    return dict(interpolated=predicted, left_only=a, quarter_period_control=(predicted+PERIOD/4) % PERIOD)


def hits(queries, observed_hz, observed_phase, frequency_limit, phase_limit):
    """Union of complete hypotheses. Carrier and phase must agree on the same bracket."""
    result = dict.fromkeys(("carrier_only", *PHASES), False)
    for query in queries:
        if not any(abs(hz-observed_hz) <= frequency_limit for hz in query["centers_hz"]):
            continue
        result["carrier_only"] = True
        for method in PHASES:
            result[method] |= abs(remainder(query["phase"][method]-observed_phase, PERIOD)) <= phase_limit
    return result
