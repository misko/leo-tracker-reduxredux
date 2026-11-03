"""Metadata-only checking split: every third visit within each channel."""


def checking_visits(channel_visits):
    by_channel = {}
    for channel, visit in channel_visits:
        by_channel.setdefault(channel, set()).add(visit)
    # Keep every receiver, probe and detector alternative from one visit together.
    return frozenset((channel, visit) for channel, visits in by_channel.items()
                     for visit in sorted(visits)[2::3])
