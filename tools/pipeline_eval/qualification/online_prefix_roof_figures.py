"""Export the pilot's four checkpoint series under their exact roof recording identities."""

import gzip
import json

from ..__main__ import save_json, write
from .online_prefix import HORIZONS
from .online_prefix_trial import CASES, OUT
from .portable_gate_trials import checksum, compressed_rows


def export(report):
    incoming = report / "positions.jsonl.gz"
    seal = json.loads((report / "figure-lock.json").read_bytes())
    if seal["files"][incoming.name] != checksum(incoming):
        raise ValueError("pilot figure predictions changed after seal")
    original = list(map(json.loads, gzip.decompress(incoming.read_bytes()).splitlines()))
    rows = []
    for checkpoint in HORIZONS:
        group = [
            r for r in original if r["condition"] == "matched" and r.get("checkpoint") == checkpoint
        ]
        assert {r["recording"] for r in group} == set(CASES) and len(group) == len(CASES)
        rows.extend(dict(row, id=row["recording"]) for row in group)
    file = report / "roof-checkpoints.jsonl.gz"
    write(file, compressed_rows(rows))
    save_json(
        report / "roof-checkpoint-lock.json",
        dict(cases=list(CASES), files={file.name: checksum(file)}),
    )


if __name__ == "__main__":
    export(OUT)
