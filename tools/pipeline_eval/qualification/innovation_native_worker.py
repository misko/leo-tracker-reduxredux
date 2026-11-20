import json
import sys
from functools import partial
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    start = native._now()
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    from innovation_parent import worker as parent_worker

    from tools.pipeline_eval.variants import innovation_native, innovation_noise

    constructor = partial(
        innovation_native.CompiledFilter, run=innovation_native.kernel("/worker/innovation.so")
    )
    initial = native._elapsed(start)
    with patch.object(innovation_noise, "InnovationFilter", constructor):
        out = parent_worker(request)
    for key, value in initial.items():
        out["stages"]["backend_import"][key] += value
    out["result"]["boundary"] = (
        "Complete native GLRT and compiled scalar innovations through joint receiver position"
    )
    out["worker"] = native._elapsed(start)
    return out


if __name__ == "__main__":
    json.dump(worker(json.load(sys.stdin)), sys.stdout, allow_nan=False, sort_keys=True)
