"""Disprove a terminal veto using the first inside witness for receiver 1."""

from math import isfinite

from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import probe_layout


RECEIVER = 1


def disprove(points, width_km, receiver_score):
    """Return a terminal disproof or defer to the unchanged two-receiver reducer."""
    try:
        eligible, remaining = probe_layout(points, width_km)
        if not eligible:
            return None
        scores = [receiver_score(points[index]) for index in eligible]
        if not all(map(isfinite, scores)):
            return None
        upper = max(scores)
        if scores.count(upper) != 1:
            return None
        witness = next(points[index] for index in remaining if points[index]["side"] == "inside")
        inside = receiver_score(witness)
        if isfinite(inside) and inside > upper:
            return dict(would_withhold=False, complete=False, probes_evaluated=len(eligible) + 1,
                        stop="single_receiver_inside_score")
    except (AttributeError, KeyError, StopIteration, TypeError, ValueError, OverflowError):
        pass
    return None
