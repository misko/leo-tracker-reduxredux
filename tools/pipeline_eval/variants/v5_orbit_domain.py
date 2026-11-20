"""Supply causal orbit support to the compact v5 initial-corner projection."""

import json
import sys
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.variants import orbit_projector, v5_lean, v5_secant_fit

BOUNDARY = "Complete native factors to compact v5 cavity with causal initial-corner orbit support"
OUTSIDE = "orbit phase interpolation never extrapolates"
# The frozen reassociation screen already searches this along-orbit phase interval.
PHASE_LIMIT_S = 30.0
DERIVATIVE_STEP_S = 0.05
NOMINAL_PAD_S = 17.0


def support_knots(knots, times, phases, *, derivative_step_s):
    knots, times, phases = (np.asarray(value, float) for value in (knots, times, phases))
    if (
        knots.ndim != 1 or len(knots) < 2 or not np.all(np.diff(knots) == 1.0)
        or times.ndim != 1 or not len(times) or not np.isfinite(times).all()
        or phases.ndim != 1 or not len(phases) or not np.isfinite(phases).all()
        or np.any(abs(phases) > PHASE_LIMIT_S) or derivative_step_s != DERIVATIVE_STEP_S
        or knots[0] != -NOMINAL_PAD_S or times.min() < 0
        or times.max() > knots[-1] - NOMINAL_PAD_S
    ):
        raise ValueError("corner orbit query lies outside the admissible causal support domain")
    lo = int(np.floor(times.min() + (phases.min() - derivative_step_s)))
    hi = int(np.ceil(times.max() + (phases.max() + derivative_step_s)))
    return np.r_[np.arange(lo, knots[0]), np.arange(knots[-1] + 1.0, hi + 1.0)]


def splice_bank(bank, extra_times, positions, velocities):
    """Preserve all original states; insert only independently propagated knots."""
    times = bank["time_s"]
    left = int(np.searchsorted(extra_times, times[0]))
    return dict(
        time_s=np.r_[extra_times[:left], times, extra_times[left:]],
        position_km=np.concatenate(
            (positions[:, :left], bank["position_km"], positions[:, left:]), axis=1
        ),
        velocity_km_s=np.concatenate(
            (velocities[:, :left], bank["velocity_km_s"], velocities[:, left:]), axis=1
        ),
    )


def propagation_times(original, extra):
    """Supply the frozen propagator's three-instant minimum using existing states."""
    if len(extra) >= 3:
        return extra
    side = original[:2] if extra[0] < original[0] else original[-2:][::-1]
    return np.sort(np.r_[extra, side[:3 - len(extra)]])


def worker(request, result, library):
    from leo.analysis.localization_v3 import discovery, scan
    from leo.analysis.localization_v3.orbits import ecef_states

    from leo.operations import localization_v3_inputs
    from leo.sky.propagation import ElementSetCatalogue

    original_bank = localization_v3_inputs.regional_bank
    original_explore = discovery.explore
    original_shifted = scan.ScanLikelihood.shifted
    nominal = {}
    work = dict(corner_projections_extended=0, sgp4_calls=0, sgp4_state_count=0, new_state_count=0,
                support_wall_s=0.0, max_augmented_bank_bytes=0, added_knots_s=[])

    def regional(catalogue, origin, *args, **kwargs):
        result = original_bank(catalogue, origin, *args, **kwargs)
        nominal.update(origin=origin, catalogue=result["catalogue"], bank=result["bank"])
        return result

    def explore(context, state, anchor, method, *args, **kwargs):
        if method != "receiver_smooth" or not np.array_equal(
            np.abs(anchor), [context.search_region.half_width_km] * 2
        ):
            return original_explore(context, state, anchor, method, *args, **kwargs)
        states = {}

        def shifted(owner, base, phases, point, extra=None):
            if owner is not context or extra is not None:
                return original_shifted(owner, base, phases, point, extra)
            original_prepare = scan.prepare_phase_geometry

            def prepare(bank, times, active_phases, *, derivative_step_s=DERIVATIVE_STEP_S):
                try:
                    return original_prepare(
                        bank, times, active_phases, derivative_step_s=derivative_step_s
                    )
                except ValueError as error:
                    if str(error) != OUTSIDE:
                        raise
                started = perf_counter()
                if (
                    context.origin_utc_ns != nominal["origin"]
                    or not np.array_equal(context.norads, nominal["bank"]["norad"])
                    or not np.array_equal(bank["time_s"], nominal["bank"]["time_s"])
                    or not np.isfinite(phases).all()
                ):
                    raise ValueError("corner projection does not bind its causal orbit bank")
                rows = np.flatnonzero(abs(phases) > 1e-9)
                source = nominal["bank"]
                if not len(rows) or any(
                    not np.array_equal(bank[key], source[key][rows])
                    for key in ("position_km", "velocity_km_s")
                ):
                    raise ValueError("corner projection rows disagree with causal SGP4 inputs")
                knots = support_knots(bank["time_s"], times, active_phases,
                                      derivative_step_s=derivative_step_s)
                if not len(knots):
                    raise ValueError("corner projection did not identify required causal knots")
                key = tuple(rows), tuple(knots)
                if key not in states:
                    cat = nominal["catalogue"]
                    selected = ElementSetCatalogue(
                        tuple(cat.names[i] for i in rows),
                        tuple(cat.satellite_numbers[i] for i in rows),
                        tuple(cat.satellites[i] for i in rows),
                    )
                    requested = propagation_times(bank["time_s"], knots)
                    p, v, usable = ecef_states(selected, context.origin_utc_ns, requested)
                    if not usable.all() or not np.isfinite(p).all() or not np.isfinite(v).all():
                        raise ValueError("causal orbit extension propagation failed")
                    added = np.isin(requested, knots)
                    original = np.searchsorted(bank["time_s"], requested[~added])
                    if not (
                        np.array_equal(p[:, ~added], bank["position_km"][:, original])
                        and np.array_equal(v[:, ~added], bank["velocity_km_s"][:, original])
                    ):
                        raise ValueError("causal orbit extension did not reproduce the seam")
                    states[key] = splice_bank(bank, knots, p[:, added], v[:, added])
                    work["sgp4_calls"] += 1
                    work["sgp4_state_count"] += len(rows) * len(requested)
                    work["new_state_count"] += len(rows) * len(knots)
                    work["added_knots_s"] = sorted(set(work["added_knots_s"]).union(knots.tolist()))
                    work["max_augmented_bank_bytes"] = max(
                        work["max_augmented_bank_bytes"],
                        sum(a.nbytes for a in states[key].values()),
                    )
                stencil = original_prepare(states[key], times, active_phases,
                                           derivative_step_s=derivative_step_s)
                work["corner_projections_extended"] += 1
                work["support_wall_s"] += perf_counter() - started
                return stencil

            with patch.object(scan, "prepare_phase_geometry", prepare):
                return original_shifted(owner, base, phases, point, extra)

        with patch.object(scan.ScanLikelihood, "shifted", shifted):
            return original_explore(context, state, anchor, method, *args, **kwargs)

    try:
        with (patch.object(localization_v3_inputs, "regional_bank", regional),
              patch.object(discovery, "explore", explore)):
            v5_secant_fit.worker(request, result, library, "secant")
    finally:
        save_json(Path(result).with_name("orbit-support.json"), work)
    out = json.loads(Path(result).read_bytes())
    out["metrics"]["orbit_support"] = work
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
