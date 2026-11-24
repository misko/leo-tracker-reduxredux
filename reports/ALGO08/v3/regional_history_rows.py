"""Restrict historical TLE row iteration after the original sky has selected its satellites."""

from contextlib import contextmanager
from functools import lru_cache
from time import process_time_ns
from unittest.mock import patch


class HistoryRows:
    def __init__(self, catalogue_type, counters):
        self.catalogue_type = catalogue_type
        self.counters = counters
        self.numbers = None
        # Store only indices and the number tuples. No extra SGP4 objects or orbit data.
        self.indices = lru_cache(maxsize=32)(self._indices)

    def select(self, numbers):
        if self.numbers != numbers:
            self.indices.cache_clear()
            self.numbers = numbers

    def _indices(self, numbers):
        return tuple(i for i, number in enumerate(numbers) if number in self.numbers)

    def filter(self, catalogue):
        if type(catalogue) is not self.catalogue_type or self.numbers is None:
            return catalogue
        numbers = catalogue.satellite_numbers
        keep = self.indices(numbers)
        self.counters["history_input_rows"] += len(numbers)
        self.counters["history_retained_rows"] += len(keep)
        return self.catalogue_type(
            tuple(catalogue.names[i] for i in keep), tuple(numbers[i] for i in keep),
            tuple(catalogue.satellites[i] for i in keep), tuple(catalogue.epochs[i] for i in keep))


@contextmanager
def measured_history(enabled, counters):
    from leo.operations import localization_v3_inputs as inputs
    from tools.pipeline_eval.variants.algo08_causal_reuse import PreparedCatalogue

    counters.update(history_input_rows=0, history_retained_rows=0, sky_cpu_ns=0, history_cpu_ns=0)
    views = HistoryRows(PreparedCatalogue, counters)
    sky, phase, bank = inputs.prepare_initial_sky, inputs.prepare_phase_history, inputs.regional_bank

    def sky_window(*args, element_parser, **kwargs):
        start = process_time_ns()
        try:
            if not enabled:
                return sky(*args, element_parser=element_parser, **kwargs)
            views.select(None)

            def full_bank(*bank_args, **bank_kwargs):
                result = bank(*bank_args, **bank_kwargs)
                views.select(frozenset(result["catalogue"].satellite_numbers))
                return result

            def parsed(text):
                return views.filter(element_parser(text))

            with patch.object(inputs, "regional_bank", full_bank):
                return sky(*args, element_parser=parsed, **kwargs)
        finally:
            counters["sky_cpu_ns"] += process_time_ns() - start

    def phase_window(reader, elements, metadata, *, element_parser):
        start = process_time_ns()
        try:
            if enabled and all(isinstance(key, str) and key.isascii() and key.isdecimal()
                               and str(int(key)) == key for key in elements):
                views.select(frozenset(map(int, elements)))
                return phase(reader, elements, metadata, element_parser=lambda text: views.filter(element_parser(text)))
            return phase(reader, elements, metadata, element_parser=element_parser)
        finally:
            counters["history_cpu_ns"] += process_time_ns() - start

    with patch.object(inputs, "prepare_initial_sky", sky_window), patch.object(inputs, "prepare_phase_history", phase_window):
        yield


def main():
    import argparse
    import json
    from pathlib import Path
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import continued_cfo_trial
    import unified_short_bootstrap as entry

    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("baseline", "candidate"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    counters = {}
    original = entry.publish_active

    def publication(*positional, **kwargs):
        with measured_history(args.mode == "candidate", counters):
            return original(*positional, **kwargs)

    with patch.object(entry, "publish_active", publication):
        continued_cfo_trial.work(args.root)
    (args.root / "history-rows.json").write_text(json.dumps(counters, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
