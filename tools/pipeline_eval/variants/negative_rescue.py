"""Retain all stock-positive packets and admit independently detected rescues."""

GATE = "passed_fractional_margin_gate"


def positive(probe):
    return any(candidate[GATE] is True for candidate in probe["candidates"])


def misses(probes):
    """The paired detector needs a second invocation if either stereo lane misses."""
    return not all(map(positive, probes))


def select(stock, differential):
    """Select one complete authentic packet at the current physical receiver."""
    if positive(stock) or not positive(differential):
        return stock
    return differential
