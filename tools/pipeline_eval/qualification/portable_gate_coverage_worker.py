"""Run the locked held-support receiver in the portable sandbox."""

import json
import sys
from pathlib import Path

from leo.analysis.localization_v4.backend import ProcessBound

from tools.pipeline_eval.variants import portable_gate_coverage, portable_v5

packet = json.load(sys.stdin)
document = packet["document"]
cutoff = document["clock_anchor"]["before"]["realtime_ns"]
result = portable_gate_coverage.run(
    document,
    tile=packet["tile"],
    archive=portable_v5.SnapshotArchive(packet["history"], cutoff, "/history"),
    bound=ProcessBound(Path(sys.argv[1]), Path("/tmp/native-receipts")),
    library=Path("/kernel/projector.so"),
)
json.dump(result, sys.stdout, separators=(",", ":"), allow_nan=False)
