"""Retain a bounded set of validated elements until this request elects its rows."""

from collections import Counter, OrderedDict
from contextlib import contextmanager
from functools import partial
from hashlib import sha256


ORIGINAL_SOURCE = "b1d43a1593d25e6232dd8c37b0e548015ca19de10359c43c22e483fb3f8285fe"
RETENTION_SOURCE = "bc683d28d4a05dfa3c3f4631736fecae8ea77ed988ea106ad7f4b11c113303bf"


def private_source(original):
    """Reconstruct the measured prototype solely in this experiment's scratch."""
    if sha256(original).hexdigest() != ORIGINAL_SOURCE:
        raise ValueError("Expected the frozen original historical orbit source")
    source = original.decode("utf-8")
    changes = (
        ("    def __init__(self):\n        self.bodies = {}\n        self.pairs = {}\n",
         "    def __init__(self, *, constructor=None):\n        self.bodies = {}\n        self.pairs = {}\n"
         "        self.constructor = constructor\n"),
        ("        names, numbers, pairs, epochs = [], [], [], []\n",
         "        names, numbers, pairs, epochs = [], [], [], []\n"
         "        construct = self.constructor or installed.Satrec.twoline2rv\n"),
        ("satellite = installed.Satrec.twoline2rv(*lines)", "satellite = construct(*lines)"),
        ("def elected_elements():", "def elected_elements(constructor=None):"),
        ("    catalogue_type, original_export = causal.ElementSetCatalogue, inputs.export_tle\n",
         "    catalogue_type, original_export = causal.ElementSetCatalogue, inputs.export_tle\n"
         "    construct = constructor or inputs.Satrec.twoline2rv\n"),
        ("satellite = inputs.Satrec.twoline2rv(*pair)", "satellite = construct(*pair)"),
        ("*, index_factory=SourceIndex):", "*, index_factory=SourceIndex, element_scope=elected_elements):"),
        ("with (elected_elements() as materialized,", "with (element_scope() as materialized,"),
    )
    for needle, replacement in changes:
        if source.count(needle) != 1:
            raise ValueError("The candidate constructor hook is ambiguous")
        source = source.replace(needle, replacement)
    payload = source.encode("utf-8")
    if sha256(payload).hexdigest() != RETENTION_SOURCE:
        raise ValueError("The isolated constructor prototype changed")
    return payload


class ScanElements:
    def __init__(self, construct, limit=24_576):
        if type(limit) is not int or limit <= 0:
            raise ValueError("Expected a positive scan element limit")
        self.construct = construct
        self.limit = limit
        self.pending = OrderedDict()
        self.counts = Counter()

    def after_parse(self, first, second):
        obj = self.construct(first, second)
        if len(self.pending) == self.limit:
            self.pending.popitem(last=False)
            self.counts["evicted"] += 1
        self.pending[first, second] = obj
        self.counts["metadata_constructions"] += 1
        return obj

    def elected(self, first, second):
        obj = self.pending.pop((first, second), None)
        if obj is not None:
            self.counts["reused_elected"] += 1
            return obj
        self.counts["elected_constructions"] += 1
        return self.construct(first, second)

    @contextmanager
    def scope(self):
        from historical_orbit_index import elected_elements

        try:
            with elected_elements(self.elected) as counts:
                yield counts
        finally:
            self.counts["released_unused"] = len(self.pending)
            self.pending.clear()

    def index_factory(self):
        from historical_orbit_index import SourceIndex

        return partial(SourceIndex, constructor=self.after_parse)
