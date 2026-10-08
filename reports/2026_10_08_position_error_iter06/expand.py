"""Run the predeclared regression/replication cohort with no outcome exclusions."""

import json
import sys
from pathlib import Path

from regions import run

if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    protocol = json.loads((here / "protocol.json").read_text())
    shard = int(sys.argv[1])
    assert shard in (0, 1)
    for label in protocol["regression_labels"][shard::2] + protocol["newer_labels"][shard::2]:
        run(label, [protocol["separation_km"]])
