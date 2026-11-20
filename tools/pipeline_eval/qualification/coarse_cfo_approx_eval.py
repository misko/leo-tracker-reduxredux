"""Measure the exact same selected proposal with only the repair removed."""

import argparse
import gzip
from pathlib import Path
from unittest.mock import patch

from ..__main__ import encoded, write
from ..variants import coarse_cfo
from . import coarse_cfo_eval as trial
from . import fft_length_eval
from .full_v5_check import _sha


def replay(work, ident):
    lock, policy, producer, windows = trial.inputs(work, ident, "held")
    selected = work / "selection-lock.json"
    selection = trial.read(selected)
    if _sha(work / "input-lock.json") != selection["lock_sha256"]:
        raise ValueError("approximation must use the original development selection")
    terms = selection["selected"]
    base = trial.comparison(lock)
    base.pop("full512").clear_cache()
    base["unrepaired"] = coarse_cfo.Interpolated(
        lock["libraries"][str(terms)]["path"], terms, base["full256"]
    )
    rows = []
    libraries = fft_length_eval.base_libraries()
    try:
        with patch.object(trial, "MODES", tuple(base)):
            for i, (fields, window) in enumerate(windows):
                result = trial.one(window, policy, base, libraries, i, fields["probes_sha256"])
                rows.append(dict(visit=fields["visit"], **result))
                print(ident, fields["visit"], result["comparisons"]["unrepaired"], flush=True)
    finally:
        for grid in base.values():
            grid.clear_cache()
    raw = encoded(
        dict(
            ident=ident,
            producer=producer,
            selection_sha256=_sha(selected),
            rows=rows,
            program_sha256=_sha(Path(__file__)),
        )
    )
    write(work / f"{ident}-unrepaired.json.gz", gzip.compress(raw, mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("case", choices=tuple(trial.CASES))
    cli = parser.parse_args()
    replay(cli.work, cli.case)
