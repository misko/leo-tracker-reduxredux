"""Measure both prep-stream workers while draining only the candidate history cache."""

import json
import sys
from contextlib import nullcontext
from pathlib import Path

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification import prep_stream_worker
from tools.pipeline_eval.variants import history_stream_prep


def worker(request, result, library, mode):
    with history_stream_prep.history_cache() if mode == "history" else nullcontext([]) as history:
        prep_stream_worker.worker(request, result, library, "stream")
    path = Path(result)
    value = json.loads(path.read_bytes())
    if mode == "history":
        value["boundary"] = history_stream_prep.BOUNDARY
        value["metrics"]["history_stream_cache"] = history
    save_json(path, value)


if __name__ == "__main__":
    worker(*sys.argv[1:])
