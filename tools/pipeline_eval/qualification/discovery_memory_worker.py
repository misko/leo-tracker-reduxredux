"""Measure sparse discovery with the same stage observers as composed v5."""

import sys
from functools import partial
from unittest.mock import patch

from tools.pipeline_eval.qualification import composed_memory_worker
from tools.pipeline_eval.variants import v5_composed_memory, v5_sparse_discovery


def worker(request, result, library):
    measured = partial(v5_sparse_discovery.measured_worker, v5_composed_memory.worker)
    with patch.object(v5_composed_memory, "worker", measured):
        composed_memory_worker.worker(request, result, library)


if __name__ == "__main__":
    worker(*sys.argv[1:])
