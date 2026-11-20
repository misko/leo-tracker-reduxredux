"""Data-only joint pass worker."""

import json
import sys
from types import SimpleNamespace

from tools.pipeline_eval.variants.joint_pass_id import run

packet = json.load(sys.stdin)
capture = packet["capture"]
capture["catalog"] = capture["catalog"].encode("ascii")
result = run(SimpleNamespace(**capture), tile=packet["offer"])
json.dump(result, sys.stdout, allow_nan=False, separators=(",", ":"))
