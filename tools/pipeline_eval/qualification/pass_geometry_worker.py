"""Run the closest-approach receiver inside the data-only worker namespace."""

import json
import sys
from types import SimpleNamespace

from tools.pipeline_eval.variants.pass_geometry import run

packet = json.load(sys.stdin)
capture = packet["capture"]
capture["catalog"] = capture["catalog"].encode("ascii")
result = run(SimpleNamespace(**capture), tile=packet.get("tile"))
json.dump(result, sys.stdout, allow_nan=False, separators=(",", ":"))
