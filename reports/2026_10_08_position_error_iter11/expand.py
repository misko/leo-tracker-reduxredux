"""Expand unchanged timing policies without mutating sealed iteration-10 evidence."""

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_10_08_position_error_iter10"
sys.path.insert(0, str(SOURCE))
import experiment  # noqa: E402


if __name__ == "__main__":
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == digest
    experiment.HERE = HERE
    shard = int(sys.argv[1])
    assert shard in (0, 1)
    for label in protocol["labels"][shard::2]:
        if label in protocol["reused_results"]:
            path = SOURCE / "results" / f"{label}.json"
            assert hashlib.sha256(path.read_bytes()).hexdigest() == protocol["reused_results"][label]
            print(label, "reused sealed result", flush=True)
        else:
            experiment.run(label, protocol)
