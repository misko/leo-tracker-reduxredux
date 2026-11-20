"""Rotate physical RF coverage on predetermined hardware-clock dwell intervals."""

from bisect import bisect_right

from .frequency_schedule import channels


def bank_events(ident, size, bank, duration_s):
    if size not in (2, 4) or bank not in (0, 1):
        raise ValueError("rotating dwell requires two banks and two or four active channels")
    initial = channels(ident, 2)[0] - 1
    order = [(initial + offset) % 4 + 1 + bank * 4 for offset in (0, 2, 1, 3)]
    count = size // 2
    tenure = 30 * count
    active = order[:count]
    events = [(0, tuple(active))]
    for index, t in enumerate(range(tenure + bank * 15, int(duration_s) - tenure, 30)):
        active[index % count] = order[(count + index) % 4]
        events.append((t, tuple(active)))
    return events


def schedule(ident, metadata, device_by_visit, initial_counter, last_counter, sample_rate, size):
    if sample_rate <= 0 or last_counter <= initial_counter:
        raise ValueError("rotating dwell requires the physical capture sample clock")
    duration = (last_counter - initial_counter) / sample_rate
    events = [bank_events(ident, size, b, duration) for b in (0, 1)]
    starts = [[t * sample_rate for t, _ in lane] for lane in events]
    kept = []
    for visit, channel in metadata:
        when = device_by_visit[visit] - initial_counter
        if not 0 <= when <= last_counter - initial_counter or channel not in range(1, 9):
            raise ValueError("valid visit left the recorded RF or hardware clock authority")
        bank = int(channel > 4)
        i = bisect_right(starts[bank], when) - 1
        if channel in events[bank][i][1]:
            kept.append(visit)
    return kept, events
