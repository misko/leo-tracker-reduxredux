"""Data-only worker for the independently held region comparison."""

import json
import sys
from types import SimpleNamespace

from tools.pipeline_eval.variants.region_challenge import run

packet = json.load(sys.stdin)
capture = packet["capture"]
capture["catalog"] = capture["catalog"].encode("ascii")
result = run(SimpleNamespace(**capture), tile=packet["offer"])
json.dump(result, sys.stdout, allow_nan=False, separators=(",", ":"))
