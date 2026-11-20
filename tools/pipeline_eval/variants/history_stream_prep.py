"""Release a preparation-owned TLE parser cache at its final read boundary."""

import json
import sys
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import (
    orbit_projector,
    prep_stream_sky,
    v5_armijo_aligned_finish,
    v5_lean,
)

METHOD = "history_stream_prep"
BOUNDARY = "Native GLRT through complete aligned v5 with bounded sky and draining TLE history cache"


@contextmanager
def last_use(parser, receipt):
    """Reuse and release the original parser's validated records, one snapshot at a time."""
    budget = parser.maximum_bytes
    stats = parser.statistics()
    receipt.update(
        starting_entries=len(parser._records),
        starting_bytes=parser.bytes,
        released_bytes=0,
        released_entries=0,
    )
    parser.maximum_bytes = 0

    def consume(text):
        catalogue = parser(text)
        entry = parser._records.pop(text, None)
        if entry is not None:
            size = entry[1]
            parser.bytes -= size
            receipt["released_bytes"] += size
            receipt["released_entries"] += 1
        return catalogue

    try:
        yield consume
    finally:
        parser.maximum_bytes = budget
        receipt.update(
            remaining_entries=len(parser._records),
            remaining_bytes=parser.bytes,
            last_use_hits=parser.hits - stats["hits"],
            last_use_misses=parser.misses - stats["misses"],
        )


@contextmanager
def history_cache():
    from leo.application import localization_v3

    initial_parser = localization_v3.ElementParser
    history = localization_v3.prepare_phase_history
    receipts = []

    class OwnedPreparationParser(initial_parser):
        pass

    @wraps(history)
    def prepare(*args, **kwargs):
        parser = kwargs.get("element_parser")
        if type(parser) is not OwnedPreparationParser:
            return history(*args, **kwargs)
        measured = {}
        with last_use(parser, measured) as consume:
            result = history(*args, **dict(kwargs, element_parser=consume))
        receipts.append(measured)
        return result

    with (
        patch.object(localization_v3, "ElementParser", OwnedPreparationParser),
        patch.object(localization_v3, "prepare_phase_history", prepare),
    ):
        yield receipts


def worker(request, result, library):
    with prep_stream_sky.prepared_sky() as sky, history_cache() as history:
        v5_armijo_aligned_finish.worker(request, result, library)
    path = Path(result)
    value = json.loads(path.read_bytes())
    value["boundary"] = BOUNDARY
    value["metrics"]["history_stream_prep"] = dict(sky=dict(sky), history=history)
    save_json(path, value)


def run(case, work_dir):
    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    library = work_dir / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
