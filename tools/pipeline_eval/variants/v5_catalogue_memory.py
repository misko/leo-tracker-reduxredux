"""Bound catalogue propagation and retain exclusively owned residual orbit arrays."""

import sys
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import compact_finish, orbit_projector, v5_lean

SATELLITES_PER_BATCH = 256
STATE_KEYS = ("position_km", "velocity_km_s")


def bounded_states(ecef_states, catalogue, origin_utc_ns, times):
    """Preserve ordered float64 state arrays and each satellite's full time grid."""
    count = len(catalogue)
    if count <= SATELLITES_PER_BATCH:
        return ecef_states(catalogue, origin_utc_ns, times)
    shape = (count, len(times), 3)
    position, velocity = np.empty(shape), np.empty(shape)
    usable = np.empty(count, dtype=bool)
    for start in range(0, count, SATELLITES_PER_BATCH):
        stop = min(start + SATELLITES_PER_BATCH, count)
        rows = slice(start, stop)
        batch = type(catalogue)(
            catalogue.names[rows], catalogue.satellite_numbers[rows], catalogue.satellites[rows]
        )
        position[rows], velocity[rows], usable[rows] = ecef_states(batch, origin_utc_ns, times)
    return position, velocity, usable


def can_retain(bank, key):
    # One reference belongs to the bank and one is the getrefcount argument.
    # Aliases, including views retaining the base, take the copying fallback.
    if sys.getrefcount(bank[key]) != 2:
        return False
    array = bank[key]
    return (
        type(array) is np.ndarray
        and array.dtype == np.dtype(float)
        and array.flags.owndata
        and array.flags.c_contiguous
    )


def residual_bank_type(frozen_bank, validate, usage):
    class ResidualBank(frozen_bank):
        def __init__(self, bank):
            if type(bank) is not dict or not all(can_retain(bank, k) for k in STATE_KEYS):
                super().__init__(bank)
                usage["copied"] += 1
                return
            # The residual caller just created both eligible state arrays by
            # boolean indexing and drops its dictionary after construction.
            # Keep the small time grid independently immutable as in stock v5.
            times = np.asarray(bank["time_s"], float)
            entries = [(times.tobytes(), times.shape)]
            for key in STATE_KEYS:
                source = bank[key]
                source.setflags(write=False)
                entries.append((memoryview(source).toreadonly(), source.shape))
            object.__setattr__(self, "_entries", tuple(entries))
            validate(self, np.empty(0))
            usage["retained"] += 1

    return ResidualBank


@contextmanager
def catalogue_batches(*, retain=False):
    from leo.analysis.localization_v3 import reassociation_catalogue, residual_screen

    from leo.analysis.research.track_catalogue_geometry import interpolate_states

    usage = dict(retained=0, copied=0)
    bank = residual_screen.FrozenOrbitBank
    if retain:
        bank = residual_bank_type(bank, interpolate_states, usage)
    with (
        patch.object(
            residual_screen, "ecef_states", partial(bounded_states, residual_screen.ecef_states)
        ),
        patch.object(
            reassociation_catalogue,
            "ecef_states",
            partial(bounded_states, reassociation_catalogue.ecef_states),
        ),
        patch.object(residual_screen, "FrozenOrbitBank", bank),
    ):
        yield usage


def worker(request, result, library):
    with catalogue_batches(retain=True):
        compact_finish.worker(request, result, library)


def run(case, work_dir):
    from tools.pipeline_eval.__main__ import local_output

    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    library = work_dir / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
