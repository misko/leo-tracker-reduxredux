"""Run a fresh isolated native receiver with instrumented stock or cached association."""

import json
import sys
from resource import RLIMIT_AS, setrlimit

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    started = native._now()
    from tools.pipeline_eval.variants import cached_association, joint_orbits, robust_orbit_fit

    imports = native._elapsed(started)
    stock_infer = robust_orbit_fit.infer
    stock_matches = joint_orbits._matches
    stock_associate = joint_orbits.associate
    cached = request.pop("cache_association")
    matcher = cached_association.Matcher(stock_matches, cached)
    ownership = []

    def traced_associate(arcs, matches, ceiling):
        selected, moves = stock_associate(arcs, matches, ceiling)
        arc_index = {id(arc): i for i, arc in enumerate(arcs)}
        owners = [(arc_index[id(row.arc)], row.winner, row.orbit, row.alias) for row in selected]
        ownership.append(
            dict(
                ceiling=ceiling,
                selected=len(owners),
                pair_moves=moves,
                owners_sha256=native.projection_digest(owners),
            )
        )
        return selected, moves

    try:
        robust_orbit_fit.infer = joint_orbits.infer
        joint_orbits._matches = matcher
        joint_orbits.associate = traced_associate
        result = native.worker(request)
    finally:
        robust_orbit_fit.infer = stock_infer
        joint_orbits._matches = stock_matches
        joint_orbits.associate = stock_associate
    stages = result["stages"]
    stages["joint_backend"] = stages.pop("same_exact_backend")
    stages["backend_import"] = {
        key: val + stages["backend_import"][key] for key, val in imports.items()
    }
    result["association"] = matcher.receipt()
    result["ownership_passes"] = ownership
    if cached:
        result["result"]["boundary"] = cached_association.BOUNDARY
    return result


if __name__ == "__main__":
    start = native._now()
    out = worker(json.load(sys.stdin))
    out["worker"] = native._elapsed(start)
    json.dump(out, sys.stdout, sort_keys=True, allow_nan=False)
