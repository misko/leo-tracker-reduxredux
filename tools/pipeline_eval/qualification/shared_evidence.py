"""Package the two receiver experiments for archive-independent plotting and scoring."""

import argparse
import gzip
from pathlib import Path

from ..__main__ import encoded, read_predictions, references, write
from ..scoring import score
from .prefix_figures import csv_file


def pack(runs, out):
    def load(panel, method):
        refs = references(panel, None)[1]
        data = read_predictions(runs / panel / method / "current/predictions.jsonl")
        if set(data) != {r["id"] for r in refs}:
            raise ValueError(f"incomplete {panel} prediction roster")
        if any(r["result"]["status"] not in ("ok", "withheld") for r in data.values()):
            raise ValueError(f"{panel} contains an unfinished receiver result")
        return refs, data

    def save_rows(name, rows):
        write(
            out / (name + ".jsonl.gz"),
            gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0),
        )

    method = "shared_doppler"
    _, ds26 = load("ds26-common127", method)
    small, roof = load("roof16", method)
    for r in small:
        k = r["id"]
        if k in ds26 and (
            roof[k]["result"]["arms"] != ds26[k]["result"]["arms"]
            or roof[k]["implementation_sha256"] != ds26[k]["implementation_sha256"]
        ):
            raise ValueError(f"repeated single-tile result differs on {k}")
    save_rows(
        "single-tile", [*ds26.values(), *(roof[r["id"]] for r in small if r["group"] == "DS29")]
    )
    refs, transfer = load("transfer124", method)
    save_rows("transfer", transfer.values())
    summary, errors = score(refs, transfer)
    csv_file(out / "transfer-errors.csv", errors)
    write(out / "transfer-summary.json", encoded(summary) + b"\n")
    _, partial = load("smoke", "anchor_receiver")
    for key, row in partial.items():
        detector = row["artifacts"]["waveform-comparison.json"]
        if detector["case"] != key or len(detector["rows"]) != 16:
            raise ValueError(f"partial waveform roster differs on {key}")
        write(out / f"{key}-detector.json.gz", gzip.compress(encoded(detector) + b"\n", mtime=0))
    save_rows(
        "partial-iq-position",
        ({k: v for k, v in r.items() if k != "artifacts"} for r in partial.values()),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    pack(args.runs, args.out)
