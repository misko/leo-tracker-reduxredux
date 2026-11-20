"""Run the development-calibrated region gate without evaluator access."""

import json
import sys
from pathlib import Path

from leo.analysis.localization_v4.backend import ProcessBound

from tools.pipeline_eval.variants import portable_v5, tile_region_empirical

packet = json.load(sys.stdin)
document = packet["document"]
cutoff = document["clock_anchor"]["before"]["realtime_ns"]
result = tile_region_empirical.run(
    document,
    tile={k: packet["tile"][k] for k in ("center", "width_km")},
    archive=portable_v5.SnapshotArchive(packet["history"], cutoff, "/history"),
    bound=ProcessBound(Path(sys.argv[1]), Path("/tmp/native-receipts")),
    library=Path("/kernel/projector.so"),
)
json.dump(result, sys.stdout, separators=(",", ":"), allow_nan=False)
