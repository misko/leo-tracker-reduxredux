"""Audit salvage ordering, exact supports, allocated payloads and host memory."""

import json
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification import history_stream_worker
from tools.pipeline_eval.qualification.working_memory_worker import fingerprint
from tools.pipeline_eval.variants import v5_tiled_salvage


def worker(request, result, library, mode):
    from leo.analysis.localization_v3 import conservative_recovery

    rankings, outcomes = [], []

    class RankingObserver:
        def __init__(self, candidates):
            self.candidates = candidates

        def __getattr__(self, name):
            return getattr(np, name)

        def argsort(self, data):
            order = np.argsort(data)
            if data.shape == (self.candidates,):
                rankings.append(fingerprint(order))
            return order

    with ExitStack() as stack:
        usage = (
            stack.enter_context(v5_tiled_salvage.tiled_salvage()) if mode == "tile" else ({}, [])
        )
        previous = conservative_recovery.salvage

        def salvage(scan, *args, **kwargs):
            # Only this module's two roster-ranking uses are observed in each mode.
            owner = v5_tiled_salvage if mode == "tile" else conservative_recovery
            with patch.object(owner, "np", RankingObserver(len(scan.norads))):
                value = previous(scan, *args, **kwargs)
            outcomes.append(fingerprint(value))
            return value

        stack.enter_context(patch.object(conservative_recovery, "salvage", salvage))
        history_stream_worker.worker(request, result, library, "history")

    path = Path(result)
    value = json.loads(path.read_bytes())
    value["metrics"]["solver_memory"] = dict(
        rankings=rankings, outcomes=outcomes, counters=dict(usage[0]), shortlisted=usage[1]
    )
    if mode == "tile":
        value["boundary"] = v5_tiled_salvage.BOUNDARY
    save_json(path, value)


if __name__ == "__main__":
    worker(*sys.argv[1:])
