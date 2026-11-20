"""Allocate original dual-receiver visits from physical RF and clock metadata."""

from collections import Counter, defaultdict
from hashlib import sha256

CHANNELS = tuple(range(1, 9))
BIN_COUNT = 15
SALT = "whole-pass-rf-v1"
MODES = ("lanes2", "bursts2", "lanes4", "bursts4", "full")


def rank(*values):
    return sha256(":".join(map(str, (SALT, *values))).encode()).digest()


def channels(ident, count):
    if count not in (2, 4):
        raise ValueError("whole-pass policy selects two or four physical channels")
    primary = rank("bank", ident)[0] % 4 + 1
    first = (primary, primary + 4)
    opposite = (primary + 1) % 4 + 1
    return tuple(sorted(first if count == 2 else first + (opposite, opposite + 4)))


def clock_bins(clocks):
    elapsed = clocks[-1] - clocks[0]
    if elapsed <= 0 or any(a > b for a, b in zip(clocks, clocks[1:], strict=False)):
        raise ValueError("clock inputs must be in physical delivery order")
    return [(t - clocks[0]) * BIN_COUNT // (elapsed + 1) for t in clocks]


def burst_visits(ident, clock_bin, balance, count):
    total = sum(map(len, balance.values()))
    if not 0 <= count <= total:
        raise ValueError("an RF time bin cannot spend more than its valid opportunities")
    if not count:
        return []
    allocations = {c: divmod(count * len(v), total) for c, v in balance.items()}
    take = {c: n for c, (n, _) in allocations.items()}
    remaining = count - sum(take.values())
    order = sorted(balance, key=lambda c: (-allocations[c][1], rank("quota", ident, clock_bin, c)))
    for c in order[:remaining]:
        take[c] += 1
    selected = []
    for c, visits in balance.items():
        width = take[c]
        # Spread the centers across each bin without looking at any detector measurements.
        phase = 1 + rank("burst", ident, c)[0] % 3
        start = (len(visits) - width) * phase // 4
        selected.extend(visits[start : start + width])
    return selected


def schedules(ident, metadata, clocks):
    bins = clock_bins(clocks)
    physical = defaultdict(lambda: defaultdict(list))
    for visit, channel in metadata:
        if channel not in CHANNELS or visit not in range(len(bins)):
            raise ValueError("invalid chronological RF metadata")
        physical[bins[visit]][channel].append(visit)
    if len({v for v, _ in metadata}) != len(metadata):
        raise ValueError("duplicate visit in physical RF metadata")
    out = {"full": [v for v, _ in metadata]}
    for count in (2, 4):
        chosen = set(channels(ident, count))
        continuous = [v for v, c in metadata if c in chosen]
        wanted = Counter(bins[v] for v in continuous)
        bursts = sorted(
            v for b, rf in physical.items() for v in burst_visits(ident, b, rf, wanted[b])
        )
        if Counter(bins[v] for v in bursts) != wanted:
            raise ValueError("burst schedule altered the time-bin cost budget")
        out.update({f"lanes{count}": continuous, f"bursts{count}": bursts})
    return out
