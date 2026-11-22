"""Scan-scoped TLE reuse for the ALGO08 regional preparation port."""

from dataclasses import dataclass
from sys import getsizeof

from sgp4.api import Satrec, accelerated

from leo.analysis.localization_v3.elements import ElementParser
from leo.sky.propagation import ElementSetCatalogue, ElementSetError, parse_element_set_records


@dataclass(frozen=True, slots=True)
class PreparedCatalogue:
    names: tuple
    satellite_numbers: tuple
    satellites: tuple
    epochs: tuple

    def __len__(self):
        return len(self.satellites)

    def element_epoch_utc_ns(self):
        return self.epochs


class CausalPreparationParser:
    """Reuse parsed records only inside regional sky and phase-history preparation.

    The production operations read metadata and export elements, and only bulk
    SatrecArray propagation consumes the shared SGP4 objects. The accelerated
    array copies its input records. Keep the stock parser for nonaccelerated
    builds and release the cache before handing prepared inputs to inference.
    """

    def __init__(self, maximum_bytes=256 * 1024 * 1024):
        if maximum_bytes < 0:
            raise ValueError("Element cache budget must be nonnegative")
        self.maximum_bytes = maximum_bytes
        self.fallback = None if accelerated and maximum_bytes else ElementParser(maximum_bytes)
        self.catalogues = {}
        self.elements = {}
        self.retained_bytes = 0
        self.stats = dict(snapshot_hits=0, snapshot_misses=0, element_hits=0,
                          element_misses=0, retained_peak_bytes=0, fallback_calls=0)

    def _remember(self, cache, key, value, size):
        # Mapping entries and allocator slack are not included in the estimate.
        total = self.retained_bytes + size
        if total > self.maximum_bytes:
            self.catalogues.clear()
            self.elements.clear()
            self.retained_bytes = 0
            self.fallback = ElementParser(self.maximum_bytes)
            return
        cache[key] = value
        self.retained_bytes = total
        self.stats["retained_peak_bytes"] = max(self.stats["retained_peak_bytes"], total)

    def _element(self, record):
        key = record.first_line, record.second_line
        cached = self.elements.get(key)
        if cached is not None:
            self.stats["element_hits"] += 1
            return cached
        self.stats["element_misses"] += 1
        try:
            satellite = Satrec.twoline2rv(*key)
        except (ValueError, RuntimeError) as error:
            raise ElementSetError(
                f"unparsable element set for catalog object {record.satellite_number}"
            ) from error
        number = int(satellite.satnum)
        epoch, = ElementSetCatalogue((), (), (satellite,)).element_epoch_utc_ns()
        cached = number, satellite, epoch
        self._remember(self.elements, key, cached,
                       getsizeof(key) + getsizeof(cached)
                       + sum(map(getsizeof, key)) + sum(map(getsizeof, cached)))
        return cached

    def __call__(self, text):
        if self.fallback is not None:
            self.stats["fallback_calls"] += 1
            return self.fallback(text)
        cached = self.catalogues.get(text)
        if cached is not None:
            self.stats["snapshot_hits"] += 1
            return cached
        self.stats["snapshot_misses"] += 1
        records = parse_element_set_records(text)
        elements = []
        for record in records:
            elements.append(self._element(record))
            if self.fallback is not None:
                return self(text)
        names = tuple(record.name for record in records)
        numbers, satellites, epochs = zip(*elements, strict=True)
        value = PreparedCatalogue(names, numbers, satellites, epochs)
        self._remember(self.catalogues, text, value,
                       getsizeof(text) + getsizeof(value)
                       + sum(map(getsizeof, (names, numbers, satellites, epochs)))
                       + sum(map(getsizeof, names)))
        return value


def prepare(prepare_native_scan, *args, statistics, **kwargs):
    """Bind the scan-scoped parser through the production preparation argument."""
    parser = CausalPreparationParser()
    try:
        return prepare_native_scan(*args, element_parser=parser, **kwargs)
    finally:
        for key, value in parser.stats.items():
            statistics[key] = max(statistics.get(key, 0), value) if key.endswith("peak_bytes") else (
                statistics.get(key, 0) + value
            )
