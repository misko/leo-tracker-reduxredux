"""Count exact initial projection work in the installed standalone receiver."""

import cProfile
import functools
import hashlib
import inspect
import json
import runpy
import struct
import sys
import weakref
from collections import Counter
from pathlib import Path
from time import process_time
from unittest.mock import patch


def inspect_receiver(root, flags):
    sys.path.insert(0, str(root))
    from leo.analysis.localization_v3 import families, marginal, position

    from tools.pipeline_eval.variants import orbit_projector, v5_core

    counts = Counter()
    cpu = Counter()
    basis = {}
    seen, stencil = {}, {}
    branch = -2

    def count_family_prediction(original, obj, x):
        begin = process_time()
        caller = inspect.currentframe().f_back
        while caller is not None and not caller.f_code.co_filename.endswith("/marginal.py"):
            caller = caller.f_back
        unused = caller is not None and caller.f_locals.get("aliases") is not None
        value = original(obj, x)
        key = "unused_alias_geometry" if unused else "other_alias_geometry"
        counts[key] += 1
        counts["initial_" + key] += branch >= -1
        cpu[key] += process_time() - begin
        return value

    def cache_key(problem):
        key = id(problem)
        found = basis.get(key)
        if found is None or found[0]() is not problem:
            fingerprint = hashlib.sha256()
            for vector in (problem.flat_times, problem.flat_labels, problem.reference):
                fingerprint.update(vector.tobytes())
            token = (tuple(problem.labels), tuple(problem.supported), fingerprint.digest())
            basis[key] = weakref.ref(problem), token
            return token
        return found[1]

    def projected(original, problem, xy):
        if branch >= -1:
            descriptor = cache_key(problem), xy.tobytes()
            if descriptor in seen:
                counts["fixed_phase_exact_repeat"] += 1
                counts["fixed_phase_between_branches"] += seen[descriptor] != branch
            seen.setdefault(descriptor, branch)
            counts["fixed_phase_calls"] += 1
        return original(problem, xy)

    def grid(original, projector, model, lat, lon, **kwargs):
        if branch >= -1:
            key = id(model), struct.pack("=dd", lat, lon), tuple(kwargs.items())
            found = stencil.get(key)
            if found is not None and found() is model:
                counts["full_grid_exact_repeat"] += 1
            stencil[key] = weakref.ref(model)
            counts["full_grid_calls"] += 1
        return original(projector, model, lat, lon, **kwargs)

    def initial(original, *args, **kwargs):
        nonlocal branch
        branch = -1
        try:
            return original(*args, **kwargs)
        finally:
            branch = -2

    def refresh(original, *args, **kwargs):
        nonlocal branch
        if branch >= -1:
            branch += 1
        return original(*args, **kwargs)

    profile = cProfile.Profile(timer=process_time)
    sys.argv = [str(root / "__main__.py"), *flags]
    predict = families.FixedFamilies.predicted
    evaluate = orbit_projector.Projector.evaluate
    with (
        patch.object(
            families.FixedFamilies,
            "predicted",
            lambda self, x: count_family_prediction(predict, self, x),
        ),
        patch.object(
            marginal, "_phase_geometry", functools.partial(projected, marginal._phase_geometry)
        ),
        patch.object(
            orbit_projector.Projector,
            "evaluate",
            lambda self, model, lat, lon, **kwargs: grid(evaluate, self, model, lat, lon, **kwargs),
        ),
        patch.object(
            v5_core, "initial_selection", functools.partial(initial, v5_core.initial_selection)
        ),
        patch.object(position, "refreshed", functools.partial(refresh, position.refreshed)),
    ):
        profile.enable()
        try:
            runpy.run_path(sys.argv[0], run_name="__main__")
        finally:
            profile.disable()
    rows = []
    for stat in sorted(profile.getstats(), key=lambda item: -item.inlinetime)[:75]:
        code = stat.code
        if isinstance(code, str):
            name = code
        else:
            name = code.co_filename.removeprefix(str(root) + "/") + ":" + code.co_name
        rows.append(
            dict(name=name, calls=stat.callcount, self_s=stat.inlinetime, total_s=stat.totaltime)
        )
    print(
        "profile " + json.dumps(dict(counts=counts, inspected_cpu_s=cpu, hot=rows)),
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    inspect_receiver(Path(sys.argv[1]), sys.argv[2:])
