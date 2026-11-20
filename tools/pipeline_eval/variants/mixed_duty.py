"""Pre-detector routing from admitted physical visit order and RF channel."""

PERIOD = 1024
LAST_OFFSET = 15
LANES = (1, 5, 2, 6, 3, 7, 4, 8)
METHODS = ("rotating", "fixed_phase")


def route(visits, mode):
    """Yield input visit IDs and credits online; `visits` contains only (ID, channel)."""
    if mode not in METHODS:
        raise ValueError("unknown mixed-duty route")
    last = 0
    for ordinal, (visit, channel) in enumerate(visits, 1):
        credit, wait = divmod(ordinal, PERIOD)
        if credit == last:
            continue
        target = LANES[(credit - 1) % len(LANES)]
        if mode == "fixed_phase" or channel == target or wait >= LAST_OFFSET:
            yield dict(visit=visit, ordinal=ordinal, channel=channel, target=target, credit=credit)
            last = credit
