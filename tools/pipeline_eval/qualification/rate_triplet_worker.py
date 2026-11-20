"""Read a blind capture from stdin and write a single prediction to stdout."""

import json
import sys
from time import perf_counter
from types import SimpleNamespace

from rate_triplets import METHOD, run

started = perf_counter()
request = json.load(sys.stdin)
raw = request["capture"]
capture = SimpleNamespace(**dict(raw, catalog=raw["catalog"].encode()))
result = run(capture, tile=request.get("tile"))
json.dump(
    dict(
        id=capture.case_id,
        method=METHOD,
        mode=request["mode"],
        result=result,
        worker_s=perf_counter() - started,
    ),
    sys.stdout,
    allow_nan=False,
    separators=(",", ":"),
)
