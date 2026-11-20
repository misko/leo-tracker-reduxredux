"""Capture the per-time SGP4 error code for the unchanged previous-orbit assertion."""

import sys
from pathlib import Path

import numpy as np
from sgp4.api import SGP4_ERRORS

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification.orbit_domain_diagnostic import inspect_error
from tools.pipeline_eval.variants import v5_secant_fit


def propagation_codes(catalogue, origin, times):
    from leo.sky.propagation import propagate_grid
    from leo.sky.sampling import SamplingGrid

    utc = origin + np.rint(times * 1e9).astype(np.int64)
    state = propagate_grid(catalogue, SamplingGrid(tuple(map(int, utc)), 0, 1.0))
    return state.error_code, utc


def worker(request, result, library):
    from leo.analysis.localization_v3.orbits import ecef_states

    from leo.sky.propagation import parse_element_sets

    try:
        v5_secant_fit.worker(request, result, library, "secant")
    except AssertionError as error:
        frame = error.__traceback__
        while frame.tb_next:
            frame = frame.tb_next
        trace = inspect_error(error)
        if frame.tb_frame.f_code.co_name == "previous_bank":
            v = frame.tb_frame.f_locals
            ctx, cat, sample = (v[k] for k in ("scan", "cat", "sample"))
            codes, utc = propagation_codes(cat, ctx.origin_utc_ns, sample)
            rows = []
            for i in np.flatnonzero(~v["good"]):
                number = str(cat.satellite_numbers[i])
                element = ctx.elements[number]
                current = parse_element_sets("\n".join(element["lines"]) + "\n")
                current_codes, _ = propagation_codes(current, ctx.origin_utc_ns, sample)
                _, _, current_good = ecef_states(current, ctx.origin_utc_ns, ctx.sky["time_s"])
                rows.append(dict(
                    norad=int(number), codes=codes[i].tolist(),
                    descriptions=[SGP4_ERRORS.get(int(code), "success") for code in codes[i]],
                    current_codes=current_codes[0].tolist(),
                    current_full_grid_valid=bool(current_good[0]),
                    previous_authority=ctx.previous_sources[number],
                    current_authority=element["provenance"],
                ))
            trace.update(
                origin_utc_ns=ctx.origin_utc_ns, samples_utc_ns=utc.tolist(),
                time_s=sample.tolist(), selected_current_rows=list(map(int, ctx.norads)),
                previous_tle_sha256=ctx.previous_tle_sha256, invalid_previous=rows,
            )
        save_json(Path(result).with_name("diagnostic.json"), trace)
        raise


if __name__ == "__main__":
    worker(*sys.argv[1:])
