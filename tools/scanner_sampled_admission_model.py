"""Independent discrete-event fair-admission model with polled completions.

No native SDK or numerical dependencies. Inputs are explicit sample counters,
source visits, owner delivery jitter and per-visit service costs. This does not
predict RF verdicts or generate recording evidence.
"""

import math


def simulate(geometry, rate, costs_ms, *, block_ms=20, owner_jitter_ms=(0,)):
    if rate not in (2500000, 5000000) or not isinstance(block_ms, int) or not 0 < block_ms <= 20:
        raise ValueError("unsupported delivery geometry")
    if not geometry or len(geometry) != len(costs_ms) or len(geometry) > 2500:
        raise ValueError("invalid visit inventory")
    if any(not math.isfinite(c) or not 0 < c < 450 for c in costs_ms):
        raise ValueError("service costs must be finite and below the admission-age guard")
    if not owner_jitter_ms or any(
        not math.isfinite(j) or not 0 <= j < block_ms for j in owner_jitter_ms
    ):
        raise ValueError("invalid owner delivery jitter")
    dwell_samples = rate * 120 // 1000
    if any(
        g.end - g.start != dwell_samples
        or not 0 <= g.target < 8
        or (i and g.start < geometry[i - 1].end)
        for i, g in enumerate(geometry)
    ):
        raise ValueError("invalid or overlapping dwell geometry")
    origin = geometry[0].start
    block_samples = rate * block_ms // 1000
    age_samples = rate * 120 // 1000
    fresh_samples = rate * 2500 // 1000
    seen, last = set(), {}
    pending, running = None, None
    last_pressure, source, now = None, origin, 0
    next_start, next_ready = 0, 0
    checks = []
    dropped = {name: 0 for name in ("expired", "freshness_skips", "replacements", "not_preferred")}

    def eligible(target):
        if last_pressure is None or source - last_pressure >= fresh_samples:
            return True
        overdue = {t for t in seen if t not in last or source - last[t][1] >= fresh_samples}
        return not overdue or target in overdue

    def service():
        nonlocal pending, running
        if pending is None:
            return
        i, born_ns = pending
        g = geometry[i]
        if now - born_ns > 120_000_000 or source - g.end > age_samples:
            dropped["expired"] += 1
            pending = None
        elif running is None:
            pending = None
            if not eligible(g.target):
                dropped["freshness_skips"] += 1
                return
            last[g.target] = (now, g.end)
            running = now + round(costs_ms[i] * 1e6)
            checks.append({"visit": i, "target": g.target, "started_ms": now / 1e6})

    def poll(end, index, capture=True):
        nonlocal now, running, source, next_start, next_ready, pending, last_pressure
        proposed = (end - origin) * 1_000_000_000 // rate
        proposed += round(owner_jitter_ms[index % len(owner_jitter_ms)] * 1e6)
        now = max(now, proposed)
        if running is not None and running <= now:
            running = None
        if capture:
            # A hop descriptor precedes the current block's IQ. That owner
            # call can service pending work at the previous source horizon.
            while next_start < len(geometry) and geometry[next_start].start < end:
                service()
                next_start += 1
            source = end
        service()
        if not capture:
            return
        while next_ready < len(geometry) and geometry[next_ready].end <= source:
            i = next_ready
            next_ready += 1
            g = geometry[i]
            seen.add(g.target)
            if running is not None:
                last_pressure = source
            service()
            if pending is not None:
                previous = geometry[pending[0]].target
                old_order = last.get(previous, (-1, 0))[0]
                new_order = last.get(g.target, (-1, 0))[0]
                if new_order >= old_order:
                    dropped["not_preferred"] += 1
                    continue
                dropped["replacements"] += 1
            pending = (i, now)
            service()

    end = origin
    count = 0
    for first in range(origin, geometry[-1].end, block_samples):
        end = min(first + block_samples, geometry[-1].end)
        poll(end, count)
        count += 1
    for attempt in range(100):
        if pending is None and running is None:
            break
        end += block_samples
        poll(end, count + attempt, capture=False)
    assert pending is None and running is None
    return {"checks": checks, "dropped": dropped}
