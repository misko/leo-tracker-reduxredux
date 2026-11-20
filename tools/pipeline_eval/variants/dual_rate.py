"""Select complete physical probe measurements available to a two-detector receiver."""

from .negative_rescue import select


def select_probes(fast, original, policy):
    """Choose a stereo visit, or None when the required detector has no result."""
    if policy not in ("wide", "original", "replace", "fill"):
        raise ValueError(f"unknown two-detector policy {policy!r}")
    for pair in (fast, original):
        if pair is not None and (
            len(pair) != 2
            or (pair[0]["receiver_id"], pair[1]["receiver_id"]) != (0, 1)
            or pair[0]["visit_index"] != pair[1]["visit_index"]
        ):
            raise ValueError("each input must contain one complete, ordered stereo visit")
    if fast is not None and original is not None:
        for left, right in zip(fast, original, strict=True):
            if {k: v for k, v in left.items() if k != "candidates"} != {
                k: v for k, v in right.items() if k != "candidates"
            }:
                raise ValueError("detectors disagree on the physical probe")
    if policy == "wide":
        return fast
    if policy == "original":
        return original
    if original is None:
        return fast
    if fast is None or policy == "replace":
        return original
    return tuple(select(wide, donor) for wide, donor in zip(fast, original, strict=True))


def available(finish_ns, arrival_ns, cutoff_ns, max_age_ns=None):
    """Accept detection at the boundary itself, never before its observed arrival."""
    if arrival_ns < 0 or cutoff_ns < 0 or (max_age_ns is not None and max_age_ns < 0):
        raise ValueError("receiver clocks and age limits must be nonnegative")
    if finish_ns is None:
        return False
    if finish_ns < arrival_ns:
        raise ValueError("detector completion preceded the physical arrival")
    return finish_ns <= cutoff_ns and (max_age_ns is None or finish_ns - arrival_ns <= max_age_ns)
