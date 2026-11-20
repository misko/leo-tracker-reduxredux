"""Profile selected repeated numerical keys in a capped compact receiver."""

import cProfile
import json
import pstats
import struct
import sys
import weakref
from collections import Counter, defaultdict
from contextlib import ExitStack
from functools import wraps
from hashlib import blake2b
from pathlib import Path
from time import process_time
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.qualification import cavity_lifetime_worker
from tools.pipeline_eval.variants import orbit_projector


def fingerprint(value):
    if isinstance(value, np.ndarray):
        array = value.ravel(order="K")
        return value.shape, value.dtype.str, value.strides, blake2b(array, digest_size=16).digest()
    if isinstance(value, (float, np.floating)):
        return struct.pack("=d", float(value))
    return value


def worker(unit, cpu, request, result, library, mode):
    from leo.analysis.localization_v3 import family_cavity, marginal
    from leo.analysis.localization_v4.backend import ProcessBound

    counters = defaultdict(Counter)
    shapes = defaultdict(Counter)
    weak, previous = {}, {}

    def wrap(name, call, key):
        @wraps(call)
        def invoke(*a, **kw):
            obj, signature, size, dimensions = key(a, kw)
            now = process_time()
            value = call(*a, **kw)
            elapsed = process_time() - now
            row = counters[name]
            row["calls"] += 1
            row["input_bytes"] += size
            row["cpu_s"] += elapsed
            shapes[name][str(dimensions)] += 1
            if name in weak and weak[name]() is obj and previous[name] == signature:
                row["adjacent_identity_calls"] += 1
                row["adjacent_identity_cpu_s"] += elapsed
            weak[name], previous[name] = weakref.ref(obj), signature
            return value

        return invoke

    def native(a, kw):
        arrays = [v for v in a[1:] if isinstance(v, np.ndarray)]
        signature = (
            tuple(map(fingerprint, a[1:])),
            tuple((k, fingerprint(v)) for k, v in sorted(kw.items())),
        )
        return a[0], signature, sum(x.nbytes for x in arrays), tuple(x.shape for x in arrays)

    def geometry(a, _kw):
        problem, xy = a
        arrays = (problem.reference, problem.flat_times, problem.flat_labels, xy)
        signature = (
            tuple(map(fingerprint, arrays)),
            tuple(
                id(b[k])
                for b in (problem.sky, problem.mode_bank)
                for k in ("time_s", "position_km", "velocity_km_s")
            ),
        )
        return problem, signature, sum(x.nbytes for x in arrays), (len(xy), len(problem.flat_times))

    def projector(a, kw):
        _, grid, *point = a
        sig = (
            tuple(map(fingerprint, point)),
            tuple((k, fingerprint(v)) for k, v in sorted(kw.items())),
        )
        return grid, sig, grid.bytes, (len(grid.positions), grid.index.shape[-1])

    def coarse(a, kw):
        bank, times, *point = a
        sig = (
            tuple(map(fingerprint, point)),
            fingerprint(times),
            fingerprint(kw["phase_seconds"]),
            id(bank["velocity_km_s"]),
        )
        return bank["position_km"], sig, times.nbytes, (len(bank["position_km"]), len(times))

    profile = cProfile.Profile()
    with ExitStack() as stack:
        for owner, name, key in (
            (ProcessBound, "__call__", native),
            (marginal, "_phase_geometry", geometry),
            (orbit_projector.Projector, "evaluate", projector),
            (family_cavity, "phase_frequency_grid", coarse),
        ):
            stack.enter_context(patch.object(owner, name, wrap(name, getattr(owner, name), key)))
        profile.enable()
        try:
            cavity_lifetime_worker.worker(unit, cpu, request, result, library, mode)
        finally:
            profile.disable()
            raw = pstats.Stats(profile).stats
            out = dict(
                operations={
                    k: dict(v, shapes=shapes[k].most_common(8)) for k, v in counters.items()
                },
                functions=[
                    dict(
                        function=name,
                        file=Path(path).name,
                        line=line,
                        calls=v[1],
                        self_s=v[2],
                        cumulative_s=v[3],
                    )
                    for (path, line, name), v in sorted(raw.items(), key=lambda x: -x[1][2])[:45]
                ],
            )
            Path(result).with_name("profile.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    worker(*sys.argv[1:])
