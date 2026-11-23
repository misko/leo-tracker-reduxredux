"""Seal an exact candidate/control comparison from completed saved workers."""

import argparse
from hashlib import sha256
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_bytes())


def numerical(value):
    if isinstance(value, dict):
        return {key: numerical(item) for key, item in value.items() if key != "cpu_ns"}
    if isinstance(value, list):
        return [numerical(item) for item in value]
    return value


def compare(control, borrowed):
    records = {name: load(path / "result.json") for name, path in (("control", control), ("borrow", borrowed))}
    a, b = records.values()
    if (a["mode"] != "control" or b["mode"] != "borrow"
            or any(value["clock"]["exit_code"] or not value["scientific_parity"] for value in records.values())
            or any(a[key] != b[key] for key in ("figures", "selected_rows"))
            or any(a["evidence"][key] != b["evidence"][key] for key in
                   ("arms", "owners", "raw_authority", "scientific_digests", "artifacts"))):
        raise ValueError("Candidate and control differ in published science")
    stages = [run["stages"]["work"] for run in records.values()]
    if any(numerical(stages[0][key]) != numerical(stages[1][key])
           for key in ("selected", "endpoint", "phase_reference", "ordered")):
        raise ValueError("Original cold branch signs, ordered signatures or measurements changed")
    copy, scratch = (run["solve"]["cold_track_rows"] for run in records.values())
    if (copy["copy_bytes"] <= 0 or scratch.get("borrow_requests", 0) <= 0
            or scratch.get("borrow_fallbacks", 0) or scratch.get("copy_bytes", 0)
            or scratch["borrow_backup_bytes"] >= copy["copy_bytes"]
            or any(copy[key] != scratch[key] for key in ("shared_ranks", "ordinary_ranks", "reused_requests",
                                                         "released_requests", "shifted_cells"))):
        raise ValueError("The candidate did not reduce nominal copying while preserving scope")
    return dict(exact_science=True, exact_ordered_ranks=True,
                source_receipts={str(path): sha256((path / "result.json").read_bytes()).hexdigest()
                                 for path in (control, borrowed)},
                measurements={mode: dict(clock=row["clock"], solve=row["solve"]["cpu_s"],
                                        profile=row["stages"]["work"]["scopes"][0],
                                        rank=row["stages"]["work"]["ranks"][0],
                                        association=row["solve"]["cold_track_rows"])
                              for mode, row in records.items()},
                avoided_nominal_copy_bytes=copy["copy_bytes"]-scratch["borrow_backup_bytes"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control", type=Path)
    parser.add_argument("borrowed", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.output.open("x") as stream:
        json.dump(compare(args.control, args.borrowed), stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
