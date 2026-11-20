"""Gate the original peer retry using a timer for each physical antenna and RF."""


class RetryCadence:
    def __init__(self, after, interval_ns=2_000_000_000):
        if after not in ("miss", "hit") or interval_ns < 0:
            raise ValueError("choose hit or miss and a nonnegative interval")
        self.after = after
        self.interval_ns = interval_ns
        self.next_allowed = {}

    def allows(self, key, now_ns):
        return now_ns >= self.next_allowed.get(key, now_ns)

    def observed(self, key, now_ns, hit):
        """Record an actual retry. Skipped calls never update the timer."""
        if not self.allows(key, now_ns):
            raise ValueError("cannot observe an unexecuted retry during its waiting interval")
        if hit == (self.after == "hit"):
            self.next_allowed[key] = now_ns + self.interval_ns
        else:
            self.next_allowed.pop(key, None)
