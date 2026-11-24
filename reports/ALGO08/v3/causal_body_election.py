"""Reduce repeated row elections within one verified causal preparation."""

from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from functools import wraps
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch


SOURCE_INDEX_PIN = "b1d43a1593d25e6232dd8c37b0e548015ca19de10359c43c22e483fb3f8285fe"
CACHE_LIMIT = 128
COLUMNS = ("names", "satellite_numbers", "satellites", "epochs")


def admissible(catalogue, catalogue_type):
    return (
        type(catalogue) is catalogue_type
        and all(type(getattr(catalogue, key)) is tuple and len(getattr(catalogue, key)) == len(catalogue)
                for key in COLUMNS)
    )


class LatestBodies:
    """Report every original reference, but suppress its dominated parsed rows."""

    def __init__(self, reader, cutoff):
        self.reader = reader
        self.dominant = {}
        self.last = None
        oldest = cutoff - 172_800_000_000_000
        self.snapshots = tuple(reader.list_snapshots("space-track"))
        for snapshot in self.snapshots:
            if oldest <= snapshot.collected_utc_ns <= cutoff:
                newest = self.dominant.get(snapshot.sha256)
                if newest is None or snapshot.collected_utc_ns > newest:
                    self.dominant[snapshot.sha256] = snapshot.collected_utc_ns

    def list_snapshots(self, provider):
        if provider != "space-track":
            raise ValueError("The cohort must use the installed Space-Track port")
        return self.snapshots

    def read(self, snapshot):
        text = self.reader.read(snapshot)
        self.last = snapshot
        return text

    def parser(self, original, catalogue_type, counts):
        def select(text):
            catalog = original(text)
            snapshot = self.last
            if (snapshot is not None and snapshot.collected_utc_ns < self.dominant[snapshot.sha256]
                    and admissible(catalog, catalogue_type)):
                counts["dominated_latest_references"] += 1
                counts["dominated_latest_rows"] += len(catalog)
                return replace(catalog, **dict.fromkeys(COLUMNS, ()))
            return catalog

        return select


class RegionalRows:
    """Restrict original ordered row tuples to exactly the screened numeric IDs."""

    def __init__(self, numbers, catalogue_type, counts):
        self.numbers = frozenset(numbers)
        self.catalogue_type = catalogue_type
        self.counts = counts
        self.cache = {}

    def pick(self, catalogue):
        key = id(catalogue)
        hit = self.cache.get(key)
        if hit is not None:
            self.counts["projection_hits"] += 1
            self.counts["projected_rows_not_scanned_again"] += len(catalogue) - len(hit[1])
            return hit[1]
        if len(self.cache) >= CACHE_LIMIT or not admissible(catalogue, self.catalogue_type):
            self.counts["projection_fallback"] += 1
            return catalogue
        rows = [i for i, number in enumerate(catalogue.satellite_numbers) if number in self.numbers]
        columns = {}
        for name in COLUMNS:
            values = getattr(catalogue, name)
            columns[name] = tuple(values[i] for i in rows)
        subset = replace(catalogue, **columns)
        # Keep the identity owner live for the duration of this request.
        self.cache[key] = catalogue, subset
        self.counts["projected_bodies"] += 1
        self.counts["first_projected_input_rows"] += len(catalogue)
        self.counts["first_projected_output_rows"] += len(subset)
        return subset


@contextmanager
def binding(audit):
    """Use the installed election rules with a verified subset of their operands."""
    import historical_orbit_index as historical
    from leo.operations import localization_v3_inputs as inputs
    from tools.pipeline_eval.variants.algo08_causal_reuse import PreparedCatalogue

    pinned = (sha256(Path(historical.__file__).read_bytes()).hexdigest() == SOURCE_INDEX_PIN
              and historical.installed_guard())
    counts = Counter()
    audit["admissible_source"] = pinned
    audit["counts"] = counts
    if not pinned:
        yield
        return
    ordinary_initial = inputs.prepare_initial_sky
    ordinary_region = inputs.regional_bank
    ordinary_phase = historical.phase_history
    active = None

    def eligible(parser):
        owner = getattr(parser, "__self__", parser)
        return type(owner) is historical.VerifiedIndexReader

    @wraps(ordinary_initial)
    def initial(*args, element_parser, **options):
        nonlocal active
        active = None
        if not eligible(element_parser):
            counts["initial_fallback"] += 1
            return ordinary_initial(*args, element_parser=element_parser, **options)
        # Called inside the installed exterior observer, so this is its actual
        # perturbed callable. Keep returning its unmodified catalogue object.
        original_current = inputs.causal_catalogue

        def current(reader, cutoff, *, element_parser):
            recent = LatestBodies(reader, cutoff)
            select = recent.parser(element_parser, PreparedCatalogue, counts)
            return original_current(recent, cutoff, element_parser=select)

        def region(*values, **kwargs):
            nonlocal active
            bank = ordinary_region(*values, **kwargs)
            active = RegionalRows(bank["catalogue"].satellite_numbers, PreparedCatalogue, counts)
            return bank

        def parse(text):
            catalogue = element_parser(text)
            return catalogue if active is None else active.pick(catalogue)

        with (patch.object(inputs, "regional_bank", region),
              patch.object(inputs, "causal_catalogue", current)):
            answer = ordinary_initial(*args, element_parser=parse, **options)
        counts["initial_success"] += 1
        return answer

    @wraps(ordinary_phase)
    def phase(reader, elements, metadata, *, element_parser, **options):
        nonlocal active
        selected, active = active, None
        if (selected is None or not eligible(element_parser)
                or {str(n) for n in selected.numbers} != elements.keys()):
            counts["history_fallback"] += 1
            return ordinary_phase(reader, elements, metadata, element_parser=element_parser, **options)

        def parse(text):
            return selected.pick(element_parser(text))

        counts["history_success"] += 1
        return ordinary_phase(reader, elements, metadata, element_parser=parse, **options)

    with (patch.object(inputs, "prepare_initial_sky", initial),
          patch.object(historical, "phase_history", phase)):
        yield
