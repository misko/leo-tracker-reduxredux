"""Capture the thrown orbit-support evaluation from the unmodified compact fit."""

import json
import sys
from pathlib import Path

import numpy as np

from tools.pipeline_eval.variants import v5_secant_fit


def inspect_error(error):
    frames = []
    tb = error.__traceback__
    while tb is not None:
        frame = tb.tb_frame
        frames.append((frame, tb.tb_lineno))
        tb = tb.tb_next
    result = {
        "error": str(error),
        "stack": [{"file": Path(f.f_code.co_filename).name, "call": f.f_code.co_name, "line": n}
                  for f, n in frames],
    }
    if str(error) != "orbit phase interpolation never extrapolates":
        return result
    values = frames[-1][0].f_locals
    scan = frames[-2][0].f_locals
    ctx = scan['self']
    q, knots, t = (values[name] for name in ('q', 'knots', 't'))
    witnesses = []
    for i, k, j in np.argwhere((q < knots[0]) | (q > knots[-1])):
        norad = int(ctx.norads[scan['active'][i]])
        element = ctx.elements[str(norad)]
        witnesses.append(dict(
            norad=norad, time_s=float(t[j]), query_s=float(q[i, k, j]),
            phase_s=float(values['phase'][i]), sample_offset_s=float(values['offsets'][i, k]),
            time_utc_ns=ctx.origin_utc_ns + round(t[j] * 1e9),
            query_utc_ns=ctx.origin_utc_ns + round(q[i, k, j] * 1e9),
            tle_provenance=element['provenance'],
            range_km=float(np.linalg.norm(
                values['p'][i, 0 if q[i, k, j] < knots[0] else -1] - site_ecef(ctx.center)
            )),
        ))
    return dict(result, origin_utc_ns=ctx.origin_utc_ns, bank_s=[float(knots[0]), float(knots[-1])],
                observations_s=[float(t.min()), float(t.max())], witnesses=witnesses)


def site_ecef(center):
    from leo.sky.frames import geodetic_to_ecef_km

    return geodetic_to_ecef_km(*center, 0.0)


def worker(request, result, library):
    try:
        v5_secant_fit.worker(request, result, library, "secant")
    except (ValueError, AssertionError) as error:
        path = Path(result).with_name("diagnostic.json")
        path.write_text(json.dumps(inspect_error(error), indent=2, allow_nan=False) + "\n")
        raise


if __name__ == "__main__":
    worker(*sys.argv[1:])
