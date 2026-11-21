"""Use compact v5's missing-history treatment for an unusable earlier orbit."""

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.variants import v5_secant_fit


def subset(catalogue, indexes):
    return type(catalogue)(
        *(
            tuple(field[i] for i in indexes)
            for field in (catalogue.names, catalogue.satellite_numbers, catalogue.satellites)
        )
    )


@contextmanager
def history_support():
    from leo.analysis.localization_v3 import orbit_modes, retained_position

    previous = orbit_modes.previous_bank
    parsed = orbit_modes.parse_element_sets
    excluded = set()
    calls = 0

    def isolate(scan, labels):
        nonlocal calls
        try:
            return previous(scan, labels)
        except AssertionError:
            old = parsed(scan.previous_tle)
            selected = {int(scan.norads[j]) for j in labels}
            candidates = subset(
                old, [i for i, n in enumerate(old.satellite_numbers) if n in selected]
            )
            if not candidates.satellites:
                raise
            _, _, good = orbit_modes.ecef_states(
                candidates, scan.origin_utc_ns, np.array([0.0, 150.0, 300.0])
            )
            failed = {n for n, ok in zip(candidates.satellite_numbers, good, strict=True) if not ok}
            if not failed:
                raise
            valid = subset(old, [i for i, n in enumerate(old.satellite_numbers) if n not in failed])
            excluded.update(map(int, failed))
            calls += 1

            def verified_catalogue(text):
                if text != scan.previous_tle:
                    raise ValueError("unexpected earlier catalogue")
                return valid

            with patch.object(orbit_modes, "parse_element_sets", verified_catalogue):
                return previous(scan, labels)

    with (patch.object(orbit_modes, "previous_bank", isolate),
          patch.object(retained_position, "previous_bank", isolate)):
        yield lambda: dict(unavailable_previous_norads=sorted(excluded), retries=calls)


def worker(request, result, library):
    with history_support() as receipt:
        try:
            v5_secant_fit.worker(request, result, library, "secant")
        finally:
            save_json(Path(result).with_name("history-retry.json"), receipt())


if __name__ == "__main__":
    worker(*sys.argv[1:])
