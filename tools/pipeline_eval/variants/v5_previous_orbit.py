"""Use the existing missing-history prior for isolated SGP4 decay of an earlier element."""

import json
import sys
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from weakref import WeakKeyDictionary

import numpy as np

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.variants import orbit_projector, v5_lean, v5_secant_fit

BOUNDARY = "Capture-era native factors to compact v5 cavity with a per-orbit missing-history prior"
ALIGNMENT_S = (0.0, 150.0, 300.0)
DECAY = 6


class RetryPreviousOrbit(Exception):
    """Retry one frozen previous-bank call after a verified old-only decay."""


def decayed_rows(error_codes, good):
    codes = np.asarray(error_codes)
    if codes.shape != (len(good), len(ALIGNMENT_S)) or not np.array_equal(
        (codes == 0).all(axis=1), good
    ):
        raise ValueError("previous-orbit diagnostics disagree with the propagation result")
    if not np.isin(codes, [0, DECAY]).all():
        raise ValueError("previous-orbit SGP4 failure is outside the isolated decay contract")
    return np.flatnonzero(~good)


def validate_current(scan, number, parse, propagate):
    element = scan.elements[str(number)]
    catalogue = parse("\n".join(element["lines"]) + "\n")
    matches = np.flatnonzero(scan.norads == number)
    if catalogue.satellite_numbers != (number,) or len(matches) != 1:
        raise ValueError("decayed history does not bind a unique current orbital candidate")
    current = int(matches[0])
    p, v, good = propagate(catalogue, scan.origin_utc_ns, scan.sky["time_s"])
    states = (p, v, scan.sky["position_km"][current], scan.sky["velocity_km_s"][current])
    if not good.all() or not all(np.isfinite(state).all() for state in states):
        raise ValueError("current orbit propagation failed during isolated history validation")
    return element["provenance"]


def history_guard(modes, catalogue_type, raw_propagation, receipt):
    original = modes.previous_bank
    parse = modes.parse_element_sets
    propagate = modes.ecef_states
    excluded = WeakKeyDictionary()

    def repair(scan, labels):
        omit = excluded.setdefault(scan, set())

        def usable_history(text):
            cat = parse(text)
            if not omit:
                return cat
            rows = [i for i, number in enumerate(cat.satellite_numbers) if number not in omit]
            return catalogue_type(
                tuple(cat.names[i] for i in rows), tuple(cat.satellite_numbers[i] for i in rows),
                tuple(cat.satellites[i] for i in rows),
            )

        def checked_previous(cat, origin, times):
            p, v, good = propagate(cat, origin, times)
            if good.all() or origin != scan.origin_utc_ns or not np.array_equal(times, ALIGNMENT_S):
                return p, v, good
            began = perf_counter()
            codes, times_utc_ns = raw_propagation(cat, origin, times)
            rejected = []
            for row in decayed_rows(codes, good):
                number = int(cat.satellite_numbers[row])
                current = validate_current(scan, number, parse, propagate)
                previous = scan.previous_sources[str(number)]
                rejected.append(dict(
                    norad=number, sgp4_codes=codes[row].tolist(),
                    current_authority=current, previous_authority=previous,
                ))
            omit.update(event["norad"] for event in rejected)
            receipt["events"].append(dict(
                original_prior_sha256=scan.previous_tle_sha256,
                samples_utc_ns=times_utc_ns.tolist(),
                missing_history=rejected,
                retained_history_norads=[
                    int(n) for i, n in enumerate(cat.satellite_numbers) if good[i]
                ],
            ))
            receipt["verification_wall_s"] += perf_counter() - began
            raise RetryPreviousOrbit

        with (patch.object(modes, "parse_element_sets", usable_history),
              patch.object(modes, "ecef_states", checked_previous)):
            try:
                return original(scan, labels)
            except RetryPreviousOrbit:
                began = perf_counter()
                result = original(scan, labels)
                receipt["retry_wall_s"] += perf_counter() - began
                return result

    return repair


def worker(request, result, library):
    from leo.analysis.localization_v3 import orbit_modes, retained_position

    from leo.sky.propagation import ElementSetCatalogue, propagate_grid
    from leo.sky.sampling import SamplingGrid

    def statuses(cat, origin, times):
        utc = origin + np.rint(times * 1e9).astype(np.int64)
        state = propagate_grid(cat, SamplingGrid(tuple(map(int, utc)), 0, 1.0))
        return state.error_code, utc

    receipt = dict(events=[], verification_wall_s=0.0, retry_wall_s=0.0)
    repair = history_guard(orbit_modes, ElementSetCatalogue, statuses, receipt)
    try:
        with (patch.object(orbit_modes, "previous_bank", repair),
              patch.object(retained_position, "previous_bank", repair)):
            v5_secant_fit.worker(request, result, library, "secant")
    finally:
        save_json(Path(result).with_name("previous-orbit.json"), receipt)
    out = json.loads(Path(result).read_bytes())
    out["metrics"]["previous_orbit"] = receipt
    save_json(Path(result), out)


def run(case, work_dir):
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    library = root / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    result = v5_lean.run_bound_worker(
        case, root, Path(__file__), worker_args=(str(library.resolve()),)
    )
    result["boundary"] = BOUNDARY
    return result


if __name__ == "__main__":
    worker(*sys.argv[1:])
