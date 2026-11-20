"""Local pilot evidence available before a paired 22-anchor retry."""

GATE = "passed_fractional_margin_gate"
MARGIN = "fractional_margin"
FRAME = 13_333


def phase(candidate):
    return candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]


def agrees(failed, peer, epoch, cfo):
    for low in failed:
        for high in peer:
            delta = (phase(low) - phase(high) + FRAME / 2) % FRAME - FRAME / 2
            if (
                abs(delta) <= epoch
                and abs(low["fractional_tracking_cfo_hz"] - high["fractional_tracking_cfo_hz"])
                <= cfo
            ):
                return True
    return False


def passes(policy, failed, peer):
    """Evaluate a frozen predicate on exactly one failed and one passing primary lane."""
    passing = tuple(c for c in peer if c[GATE])
    results = []
    for name, first, second in policy["clauses"]:
        if name == "failed_margin":
            results.append(any(c[MARGIN] >= first for c in failed))
        elif name == "peer_margin":
            results.append(any(c[MARGIN] >= first for c in passing))
        elif name == "agreement":
            results.append(agrees(failed, passing, first, second))
        else:
            raise ValueError(f"unknown primary evidence predicate {name}")
    if policy["operator"] == "any":
        return any(results)
    if policy["operator"] == "all":
        return all(results)
    raise ValueError("unknown retry policy operator")
