"""Execute only the frozen development expansion; no reserved validation scans."""

import json
import sys
from pathlib import Path

from run_joint import run

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    protocol = json.loads((root / "expansion-protocol.json").read_text())
    shard = int(sys.argv[1])
    assert shard in (0, 1)
    for label in protocol["labels"][shard::2]:
        run(label, variants=("matched-control", "joint-wide"))
