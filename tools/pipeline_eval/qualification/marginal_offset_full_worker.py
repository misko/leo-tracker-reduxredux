"""Add held covariance determinant audit to the frozen marginal-offset worker."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.qualification import marginal_offset_worker as base
from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    from tools.pipeline_eval.variants import marginal_offset as variant

    original = variant.held_score

    def audit(rows, state, scale):
        result = original(rows, state, scale)
        profiles = variant._profile_rows(rows, scale)
        mean = sum(
            getattr(row.arc.track.whiten, "log_volume", 0.0) / len(row.arc.track.t)
            for row in profiles
        ) / len(rows)
        result["held_relative_logdet_per_point"] = mean
        result["held_quadratic_and_phase_prior_per_point"] = (
            result["held_normalized_mean_loss"] - mean
        )
        return result

    with patch.object(variant, "held_score", audit):
        return base.worker(request)


if __name__ == "__main__":
    started = native._now()
    out = worker(json.load(sys.stdin))
    out["worker"] = native._elapsed(started)
    json.dump(out, sys.stdout, sort_keys=True, allow_nan=False)
