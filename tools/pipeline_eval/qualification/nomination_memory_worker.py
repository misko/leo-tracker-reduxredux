"""Fingerprint the exact complete nominations and original coarse screen."""

import json
import sys
from pathlib import Path
from types import FunctionType
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification import signed_context_memory_worker
from tools.pipeline_eval.qualification.working_memory_worker import fingerprint
from tools.pipeline_eval.variants import v5_nomination_memory as bounded


def stock_observer(original, observe):
    geometry, score = (
        original.__globals__[k] for k in ("phase_frequency_grid", "coarse_phase_scores")
    )
    grids = []
    minimum = None

    def projection(*args, **kwargs):
        nonlocal minimum
        f, e = geometry(*args, **kwargs)
        if not grids:
            minimum = e.min(axis=1)
        grids.append((f.nbytes, e.nbytes))
        return f, e

    def coarse(*args, **kwargs):
        result = score(*args, **kwargs)
        # The caller retains the first elevation and the latest temporary elevation.
        payload = sum(f for f, _ in grids) + grids[0][1] + grids[-1][1]
        observe(result, minimum, payload)
        grids.clear()
        return result

    return FunctionType(
        original.__code__,
        dict(original.__globals__, phase_frequency_grid=projection, coarse_phase_scores=coarse),
    )


def worker(request, result, library, stock=False):
    from leo.analysis.localization_v3 import family_cavity

    coarse, nominal = [], []

    def observe(values, elevation, payload):
        ordered = np.argsort(np.where(elevation >= 0, values["score"], np.inf))
        coarse.append(
            dict(
                rows=len(elevation),
                groups=values["aliases"].shape[1],
                grid_payload_bytes=payload,
                science_sha256=fingerprint((values, elevation, ordered)),
            )
        )

    def trace(direction, name, target):
        print(f"stage: {direction} nomination.{name}#row-{target}", flush=True)

    context = (
        patch.object(
            family_cavity,
            "nominate_families",
            stock_observer(family_cavity.nominate_families, observe),
        )
        if stock
        else bounded.nomination_memory(observe, trace)
    )
    with context:
        operation = family_cavity.nominate_families

        def full(*args, **kwargs):
            value = operation(*args, **kwargs)
            nominal.append(fingerprint(value))
            return value

        with patch.object(family_cavity, "nominate_families", full):
            signed_context_memory_worker.worker(request, result, library)
    path = Path(result)
    payload = json.loads(path.read_bytes())
    payload["metrics"]["nomination_memory"] = dict(coarse=coarse, nominations=nominal)
    if not stock:
        payload["boundary"] = bounded.BOUNDARY
    save_json(path, payload)


if __name__ == "__main__":
    worker(*sys.argv[1:])
