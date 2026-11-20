"""Run the same stored GLRT reader and Graph before each shortlist mode."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from ..variants import native_lean as native


def main():
    started = native._now()
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    request = json.load(sys.stdin)
    begin_import = native._now()
    from ..variants import robust_orbit_fit, track_quadrature

    imported = native._elapsed(begin_import)
    trial = track_quadrature.Trial(request.pop("method"))
    with patch.object(robust_orbit_fit, "infer", trial.infer):
        out = native.worker(request)
    out["result"]["boundary"] = track_quadrature.BOUNDARY
    out["stages"]["backend_import"] = imported
    out["worker"] = native._elapsed(started)
    json.dump(out, sys.stdout, sort_keys=True, allow_nan=False)


if __name__ == "__main__":
    main()
