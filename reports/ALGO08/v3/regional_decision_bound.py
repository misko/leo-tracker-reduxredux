"""Conservative upper bounds for a decision-only regional veto disproof."""

from math import fsum, isfinite, nextafter, inf


def mixture_cap(peak, endpoint_visible, catalogue):
    """Bound the full-orbit mixture using only necessary visibility.

    In real arithmetic the contribution is at most softplus(peak + log(K/N)).
    Round that substantially upward using 0.69 < ln(2) and ln(2) < 1.
    The released finite native domain keeps cumulative machine error far below
    the remaining 0.306 nat slack. The experiment audits every cap at use.
    """
    if (not isfinite(peak) or abs(peak) > 65536 or not 0 <= endpoint_visible <= catalogue <= 32768
            or catalogue < 1):
        raise ValueError("Unsupported native mixture bound inputs")
    if not endpoint_visible:
        return 0.
    bits = (catalogue // endpoint_visible).bit_length() - 1
    return nextafter(max(peak - .69 * bits, 0.) + 1., inf)


def below(known, unknown, denominator, inside):
    """Compare with upward accumulation guard and leave ties to the released path."""
    if denominator < 1 or not isfinite(inside) or not all(isfinite(x) and x >= 0 for x in (*known, *unknown)):
        return False
    total = fsum((*known, *unknown))
    # The released reducer sums in original order. This bound admits its
    # worst-case positive binary64 accumulation over the accepted track count.
    terms = len(known) + len(unknown)
    if terms > 4096:
        return False
    error = (terms + 3) * 2.0**-51 * total + 2.0**-1022
    return nextafter((total + error) / denominator, inf) < inside


def disprove(points, width, inside_score, exterior_loses):
    """Any strict single-receiver interior witness excludes the bilateral veto."""
    from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import probe_layout

    try:
        eligible, remaining = probe_layout(points, width)
        if not eligible:
            return None
        inside = next(points[i] for i in remaining if points[i]["side"] == "inside")
        threshold = inside_score(inside)
        if not isfinite(threshold):
            return None
        if all(exterior_loses(points[i], threshold) for i in eligible):
            return dict(would_withhold=False, complete=False, stop="bounded_single_receiver_inside_score",
                        probes_evaluated=len(eligible)+1)
    except (AttributeError, KeyError, StopIteration, TypeError, ValueError, OverflowError):
        pass
    return None
