"""Causal retry timer after two consecutive evaluated misses on one physical key."""


class TwoFailureCadence:
    INTERVAL_NS = 800_000_000

    def __init__(self):
        self.failures = {}

    def allows(self, key, now_ns):
        count, latest = self.failures.get(key, (0, now_ns))
        return count < 2 or now_ns - latest >= self.INTERVAL_NS

    def observed(self, key, now_ns, hit):
        if not self.allows(key, now_ns):
            raise ValueError("a skipped retry cannot update the failure streak")
        if hit:
            self.failures.pop(key, None)
        else:
            count, _ = self.failures.get(key, (0, now_ns))
            self.failures[key] = (min(count + 1, 2), now_ns)
