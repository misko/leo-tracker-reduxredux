"""Reuse only the released pre-RF orbital transition across chronological requests."""

from collections import Counter, OrderedDict
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch


SOURCE_SHA256 = "4659c0f6a49dbc3ae8e7f65272d2db9567dd67e6908fcb10c36bf0324decd6dd"
CAPACITY = 24_576
MISS = object()


def identity(record):
    lines, epoch, stamp = record["lines"], record["epoch"], record["collected_utc_ns"]
    if (type(lines) not in (list, tuple) or len(lines) != 2
            or type(lines[0]) is not str or type(lines[1]) is not str
            or type(epoch) is not int or type(stamp) is not int):
        return None
    return lines[0], lines[1], epoch, stamp


class OrbitUpdates:
    """A process-local LRU of frozen scalar results. All elections remain request-local."""

    def __init__(self, capacity=CAPACITY):
        if capacity < 1:
            raise ValueError("An orbital update cache must have capacity for at least one entry")
        self.capacity = capacity
        self.results = OrderedDict()
        self.cutoff = None
        self.counts = Counter()

    @contextmanager
    def request(self, prior, expected_source, cutoff):
        source = Path(prior.__file__).resolve()
        self.counts = Counter()
        code = getattr(prior.transition, "__code__", None)
        if (source != expected_source or sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256
                or getattr(prior.transition, "__module__", None) != prior.__name__
                or code is None or Path(code.co_filename).resolve() != source):
            self.results.clear()
            self.cutoff = None
            self.counts["incompatible_source"] += 1
            yield self.counts
            return
        if self.cutoff is not None and cutoff <= self.cutoff:
            self.results.clear()
            self.counts["chronology_resets"] += 1
        self.cutoff = cutoff
        original = prior.transition

        def transition(a, b, c):
            first, second, third = identity(a), identity(b), identity(c)
            if (first is None or second is None or third is None
                    or max(first[2], second[2], third[2]) > cutoff
                    or max(first[3], second[3], third[3]) > cutoff):
                self.counts["original_unsupported"] += 1
                return original(a, b, c)
            key = first, second, third
            value = self.results.get(key, MISS)
            if value is MISS:
                result = original(a, b, c)
                value = None if result is None else tuple(result.items())
                self.results[key] = value
                self.counts["misses"] += 1
                if len(self.results) > self.capacity:
                    self.results.popitem(last=False)
                    self.counts["evicted"] += 1
                return result
            self.counts["hits"] += 1
            self.results.move_to_end(key)
            return None if value is None else dict(value)

        with patch.object(prior, "transition", transition):
            yield self.counts
