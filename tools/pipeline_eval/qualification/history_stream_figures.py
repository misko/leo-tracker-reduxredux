"""Render matched position and memory figures from the sealed history trial."""

import argparse
import gzip
import json
from unittest.mock import patch

from ..__main__ import local_output
from . import prep_stream_figures
from .history_stream_trial import METHODS, PLAN, REPORT
from .prefix_figures import csv_file

SERIES = (
    (-0.18, "control", "Bounded sky only", "#476173"),
    (0.18, "history", "Final-use cache release", "#287a62"),
)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=local_output, default=REPORT)
    report = p.parse_args().report
    with patch.multiple(prep_stream_figures, METHODS=METHODS, PLAN=PLAN, SERIES=SERIES):
        rows = prep_stream_figures.data(report)
        prep_stream_figures.preparation(report, rows)
        prep_stream_figures.positions(report)
    archive = gzip.decompress((report / "history-positions.jsonl.gz").read_bytes())
    releases = {
        r["id"]: next(iter(r["result"]["metrics"].get("history_stream_cache", [])), {})
        for r in map(json.loads, archive.splitlines())
    }
    cache_keys = (
        "starting_entries",
        "starting_bytes",
        "released_entries",
        "released_bytes",
        "remaining_entries",
        "remaining_bytes",
        "last_use_hits",
        "last_use_misses",
    )
    for row in rows:
        evidence = releases[row["id"]] if row["method"] == METHODS["history"] else {}
        row.update({"drain_" + key: evidence.get(key) for key in cache_keys})
    csv_file(report / "resources.csv", rows)


if __name__ == "__main__":
    main()
