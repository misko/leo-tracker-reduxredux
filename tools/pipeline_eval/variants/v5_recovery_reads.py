"""Keep each late ECEF row block resident across every queried coarse phase."""

import inspect
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from types import FunctionType
from unittest.mock import patch

import numpy as np

from .v5_stream_recovery import BLOCK, OrbitRows

METHOD = "v5_recovery_reads"
BOUNDARY = "Complete compact v5 with orbit-row-major residual and reassociation screens"
DONORS = {
    "residual_screen": "90bf5476548e58dd164ff023f91e8c203f463a001bc6c157be0eaae5a135069f",
    "reassociation_screen": "6eec3e076e8515d282694d58f649778d144a7e5342f51f3dc297400b3458a0b7",
}


def process_io():
    with open("/proc/self/io", encoding="ascii") as stream:
        return {key: int(value) for key, value in (line.split(":") for line in stream)}


def blocks(bank):
    source, velocity = bank["position_km"], bank["velocity_km_s"]
    for start in range(0, max(1, source.shape[0]), BLOCK):
        sl = slice(start, start + BLOCK)
        yield sl, dict(time_s=bank["time_s"], position_km=source[sl], velocity_km_s=velocity[sl])


def residual_blocks(
    project, profile, bank, phases, times, query, positions, arms, rows, folds, columns, scale, best
):
    samples = {
        name: (times[query[ix]], {a: rows[a][query[ix]] for a in arms})
        for name, ix in columns.items()
    }
    for selection, orbit in blocks(bank):
        for phase in phases:
            grids = project(orbit, times, query, positions, phase_seconds=phase)
            for arm, (f, e) in zip(arms, grids, strict=True):
                f *= scale
                for name, _, _ in folds:
                    t, y = samples[name]
                    cost = (
                        profile(
                            y[arm],
                            f[:, columns[name]],
                            t,
                            rate_sigma_hz_s=0.5,
                            bias_sigma_hz=300,
                        )["cost"]
                        + (phase / 5) ** 2
                    )
                    cost = np.where(e[:, columns[name]].min(axis=1) >= 0, cost, np.inf)
                    for bound in (15, 30):
                        if abs(phase) <= bound:
                            active = best[arm][bound, name][selection]
                            np.minimum(active, cost, out=active)


def reassociation_blocks(project, profile, bank, phases, times, positions, arms, rows, scale, best):
    for selection, orbit in blocks(bank):
        for phase in phases:
            grids = project(orbit, times, positions, phase_seconds=phase)
            for arm, (f, e) in zip(arms, grids, strict=True):
                cost = (
                    profile(
                        rows[arm],
                        f * scale,
                        times,
                        rate_sigma_hz_s=0.5,
                        bias_sigma_hz=300,
                    )["cost"]
                    + (phase / 5) ** 2
                )
                active = best[arm][selection]
                np.minimum(active, np.where(e.min(axis=1) >= 0, cost, np.inf), out=active)


def overlay(operation, begin, end, replacement):
    source = inspect.getsource(operation)
    start = source.index(begin)
    stop = source.index(end, start)
    body = source[:start] + replacement + source[stop:]
    namespace = {}
    exec(compile(body, inspect.getsourcefile(operation), "exec"), namespace)
    rewritten = namespace[operation.__name__]
    bound = FunctionType(rewritten.__code__, operation.__globals__, argdefs=operation.__defaults__)
    bound.__kwdefaults__ = operation.__kwdefaults__
    return bound


@contextmanager
def recovery_reads():
    from leo.analysis.localization_v3 import (
        reassociation_admission,
        reassociation_screen,
        residual_screen,
    )

    for module in (residual_screen, reassociation_screen):
        name = module.__name__.rsplit(".", 1)[-1]
        if sha256(Path(module.__file__).read_bytes()).hexdigest() != DONORS[name]:
            raise ValueError(f"frozen late projection source changed for {name}")

    measurements = []

    def record(kind, bank, phases, operation, *args):
        source, velocity = bank["position_km"], bank["velocity_km_s"]
        if not isinstance(source, OrbitRows) or not isinstance(velocity, OrbitRows):
            raise ValueError("expected the same streamed ECEF control bank")
        before = process_io()
        wall, cpu = perf_counter(), process_time()
        operation(bank, phases, *args)
        after = process_io()
        logical = source.nbytes + velocity.nbytes
        measurements.append(
            dict(
                stage=kind,
                rows=source.count,
                knots=source.knots,
                phases=len(phases),
                state_bytes=logical,
                phase_major_state_bytes=logical * len(phases),
                state_block_bound_bytes=BLOCK * (source.row_bytes + velocity.row_bytes),
                read_bytes=after["read_bytes"] - before["read_bytes"],
                rchar=after["rchar"] - before["rchar"],
                wall_s=perf_counter() - wall,
                cpu_s=process_time() - cpu,
            )
        )

    def residual(
        project,
        profile,
        bank,
        phases,
        times,
        query,
        positions,
        arms,
        rows,
        folds,
        columns,
        scale,
        best,
    ):
        record(
            "residual",
            bank,
            phases,
            lambda b, p: residual_blocks(
                project,
                profile,
                b,
                p,
                times,
                query,
                positions,
                arms,
                rows,
                folds,
                columns,
                scale,
                best,
            ),
        )

    def reassociation(project, profile, bank, phases, times, positions, arms, rows, scale, best):
        record(
            "reassociation",
            bank,
            phases,
            lambda b, p: reassociation_blocks(
                project,
                profile,
                b,
                p,
                times,
                positions,
                arms,
                rows,
                scale,
                best,
            ),
        )

    # Only the two phase-outer sweeps change. The donor emits all fine fits,
    # policy age filters, stable global nominations, alias/margin and final receipts.
    residual_source = overlay(
        residual_screen.screen_candidates,
        "        # Stream one phase at a time",
        "        for arm in ARMS:\n            for policy,",
        """        _row_major(
            _nomination_grids, profile_rate, bank, phases, t, query, positions,
            ARMS, {a: np.asarray(target["corrected_hz"][a]) for a in ARMS},
            folds, columns, q, best,
        )
""",
    )
    reassociation_source = overlay(
        reassociation_screen.screen,
        "        for phi in np.arange(-30, 31, 2):",
        "        for a in ARMS:\n            finalists =",
        """        _row_major(
            phase_frequency_grids, profile_rate, bank, np.arange(-30, 31, 2),
            ts[ii], positions, ARMS, {a: values[a][ii] for a in ARMS}, q[ii], best,
        )
""",
    )
    with (
        patch.object(residual_screen, "_row_major", residual, create=True),
        patch.object(reassociation_screen, "_row_major", reassociation, create=True),
        patch.object(residual_screen, "screen_candidates", residual_source),
        patch.object(reassociation_admission, "screen", reassociation_source),
    ):
        yield measurements
