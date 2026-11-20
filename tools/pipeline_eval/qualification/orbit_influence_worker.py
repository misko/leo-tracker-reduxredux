"""Capture local normal equations from the actual capped native smooth worker."""

import argparse
import json
import sys
from resource import RLIMIT_AS, setrlimit
from types import SimpleNamespace
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(request, *, exact_check=False):
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    import numpy as np

    from tools.pipeline_eval.qualification import native_clock_model_worker as native_clock
    from tools.pipeline_eval.variants import joint_clock_model as clock
    from tools.pipeline_eval.variants import orbit_influence

    evidence = {}
    original = clock.infer

    def instrument(document, offer, catalogue, *, clock=True):
        from tools.pipeline_eval.variants import joint_clock_model as smooth

        contexts = {}
        refine = smooth.refine

        def retained(rows, start, tile, region, half, arm, *, clock):
            result = refine(rows, start, tile, region, half, arm, clock=clock)
            contexts[arm] = rows, start, tile, region, half, result[0].state
            return result

        with patch.object(smooth, "refine", retained):
            result = original(document, offer, catalogue, clock=clock)
        evidence["ungated"] = result
        updated = dict(result, boundary=orbit_influence.BOUNDARY)
        if result["status"] != "ok":
            return updated
        diagnostics = {}
        for arm, (rows, start, tile, region, half, state) in contexts.items():
            influence_time = native._now()
            try:
                final_rows = smooth.exact._recenter(rows, tile, region, state)
                matrix = {}

                def capture(a, b, *, bounds, matrix=matrix, **_):
                    matrix.update(a=a, b=b, bounds=bounds)
                    return SimpleNamespace(success=False)

                with patch.object(smooth.lean, "lsq_linear", capture):
                    smooth.fit(final_rows, len(tile.positions_km), half, arm, clock=clock)
                labels = [r.orbit for r in rows for _ in r.arc.track.t]
                full, covariance, shifts = orbit_influence.normal_deletions(
                    matrix["a"], matrix["b"], labels, matrix["bounds"]
                )
                diag = orbit_influence.containment(
                    state.xy, half, covariance, list(shifts.values())
                )
                diag.update(
                    orbits=len(shifts),
                    local_relinearization_shift_km=(full - state.xy).tolist(),
                    deletion_shifts_km={str(k): v.tolist() for k, v in shifts.items()},
                )
            except (ValueError, np.linalg.LinAlgError) as error:
                diag = dict(admitted=False, unavailable=str(error))
            diag["timing"] = native._elapsed(influence_time)
            if exact_check and "unavailable" not in diag:
                exact_time = native._now()
                exact_full = refine(rows, start, tile, region, np.inf, arm, clock=clock)[0].state.xy
                exact = {
                    orbit: refine(
                        [r for r in rows if r.orbit != orbit],
                        start,
                        tile,
                        region,
                        np.inf,
                        arm,
                        clock=clock,
                    )[0].state.xy
                    - exact_full
                    for orbit in shifts
                }
                check = orbit_influence.containment(
                    state.xy, half, covariance, list(exact.values())
                )
                check.update(
                    shift_error_km={
                        str(k): float(np.linalg.norm(exact[k] - shifts[k])) for k in shifts
                    },
                    timing=native._elapsed(exact_time),
                )
                diag["exact_diagnostic"] = check
            diagnostics[arm] = diag
        evidence["orbit_influence"] = diagnostics
        if len(diagnostics) != 2 or any(not d["admitted"] for d in diagnostics.values()):
            reason = (
                "orbit_influence_unavailable"
                if any("unavailable" in d for d in diagnostics.values())
                else "orbit_uncertainty_crosses_tile"
            )
            updated.update(
                status="withheld",
                reason=reason,
                arms={
                    arm: dict(value, latlon=None, region_id=None)
                    for arm, value in result["arms"].items()
                },
            )
        return updated

    with patch.object(clock, "infer", instrument):
        output = native_clock.worker(request)
    output["result"]["boundary"] = orbit_influence.BOUNDARY
    return output | evidence


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--exact-check", action="store_true")
    args = cli.parse_args()
    started = native._now()
    out = worker(json.load(sys.stdin), exact_check=args.exact_check)
    out["worker"] = native._elapsed(started)
    json.dump(out, sys.stdout, sort_keys=True, allow_nan=False)
