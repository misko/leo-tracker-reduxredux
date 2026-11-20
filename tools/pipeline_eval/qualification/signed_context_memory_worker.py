"""Trace the signed-context entry and its returned measurements on the same worker."""

import json
import sys
from functools import partial
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification import compact_memory_combined_worker
from tools.pipeline_eval.qualification.working_memory_worker import fingerprint, rss
from tools.pipeline_eval.variants import (
    v5_compact_memory_combined as combined,
)
from tools.pipeline_eval.variants import (
    v5_signed_context_memory as signed,
)


def worker(request, result, library):
    from leo.analysis.localization_v3 import signed_context

    original = signed_context.signed_context
    observed = []

    def watch(*args, **kwargs):
        print("stage: enter signed_context", flush=True)
        before, wall, cpu = rss(), perf_counter(), process_time()
        value = original(*args, **kwargs)
        observed.append(
            dict(
                before=before,
                after=rss(),
                wall_s=perf_counter() - wall,
                cpu_s=process_time() - cpu,
                digest=fingerprint(
                    {k: value[k] for k in ("arms", "signed", "all_means", "widths")}
                ),
            )
        )
        print("stage: leave signed_context", flush=True)
        return value

    composition = partial(signed.measured_worker, combined.measured_worker)
    with (
        patch.object(signed_context, "signed_context", watch),
        patch.object(combined, "measured_worker", composition),
    ):
        compact_memory_combined_worker.worker(request, result, library)
    path = Path(result)
    payload = json.loads(path.read_bytes())
    payload["metrics"]["signed_context_memory"] = observed
    save_json(path, payload)


if __name__ == "__main__":
    worker(*sys.argv[1:])
