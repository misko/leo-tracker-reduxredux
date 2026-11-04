"""Scan-scoped reuse of validated TLE text, never mutable SGP4 objects.

The complete text is the key. Collection times, causal windows and catalogue
selection remain the caller's responsibility on every invocation. Archive reads
still occur through the archive port, including its content-integrity checks.
"""
import sys
from collections import OrderedDict

from sgp4.api import Satrec

from leo.sky.propagation import ElementSetCatalogue, ElementSetError, parse_element_set_records


class ElementParser:
    def __init__(self, maximum_bytes=256 * 1024 * 1024):
        if maximum_bytes < 0:
            raise ValueError('Element cache budget must be nonnegative')
        self.maximum_bytes = maximum_bytes
        self.bytes = self.hits = self.misses = self.evictions = 0
        self._records = OrderedDict()

    def __call__(self, text):
        if text in self._records:
            self.hits += 1
            records, _ = self._records[text]
            self._records.move_to_end(text)
        else:
            self.misses += 1
            records = parse_element_set_records(text)
            size = sys.getsizeof(text) + sys.getsizeof(records)
            size += sum(sys.getsizeof(r) + sys.getsizeof(r.satellite_number)
                        + sum(sys.getsizeof(s) for s in (r.name, r.first_line, r.second_line))
                        for r in records)
            # Accounting covers retained text/records, excluding mapping overhead.
            if size <= self.maximum_bytes:
                while self.bytes + size > self.maximum_bytes:
                    _, (_, removed) = self._records.popitem(last=False)
                    self.bytes -= removed
                    self.evictions += 1
                self._records[text] = records, size
                self.bytes += size
        names, numbers, satellites = [], [], []
        for record in records:
            try:
                satellite = Satrec.twoline2rv(record.first_line, record.second_line)
            except (ValueError, RuntimeError) as error:
                raise ElementSetError(
                    f'unparsable element set for catalog object {record.satellite_number}'
                ) from error
            names.append(record.name)
            numbers.append(int(satellite.satnum))
            satellites.append(satellite)
        return ElementSetCatalogue(tuple(names), tuple(numbers), tuple(satellites))

    def statistics(self):
        return dict(hits=self.hits, misses=self.misses, evictions=self.evictions,
                    retained_bytes=self.bytes, maximum_bytes=self.maximum_bytes)
