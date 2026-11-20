"""Keep coarse causal orbit propagation and visibility scratch region-sized."""

import json
import sys
from collections import Counter
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import (
    orbit_projector,
    v5_armijo_aligned_finish,
    v5_catalogue_memory,
    v5_lean,
)

METHOD = "prep_stream_sky"
BOUNDARY = "Native GLRT through complete aligned v5 with row-bounded causal sky preparation"
COARSE_ROWS = 128


def regional_bank(
    kernel,
    usage,
    catalogue,
    origin_utc_ns,
    duration_s,
    *,
    screen_latitude_deg,
    screen_longitude_deg,
):
    """Preserve the original row-local SGP4, look-angle and threshold operations."""
    if not np.isfinite(duration_s) or duration_s < 0:
        raise ValueError("Finite nonnegative recording duration required")
    duration = max(300.0, duration_s)
    grid = np.arange(-17.0, np.ceil(duration) + 18)
    coarse = np.arange(0.0, duration + 5, 5.0)
    site = kernel.geodetic_to_ecef_km(screen_latitude_deg, screen_longitude_deg, 0.0)
    rotation = kernel.ecef_to_enu_matrix(screen_latitude_deg, screen_longitude_deg)
    cls = kernel.ElementSetCatalogue
    keep = []
    for start in range(0, len(catalogue), COARSE_ROWS):
        rows = slice(start, start + COARSE_ROWS)
        block = cls(
            catalogue.names[rows], catalogue.satellite_numbers[rows], catalogue.satellites[rows]
        )
        p, v, good = kernel.ecef_states(block, origin_utc_ns, coarse)
        angles = kernel.look_angles(p, v, site, rotation)
        keep.append(start + np.flatnonzero(good & (angles[1].max(axis=1) >= -12)))
        usage["coarse_batches"] += 1
        usage["max_coarse_rows"] = max(usage["max_coarse_rows"], len(block))
        usage["max_coarse_output_bytes"] = max(
            usage["max_coarse_output_bytes"], p.nbytes + v.nbytes + sum(a.nbytes for a in angles)
        )
        del p, v, good, angles
    selected = np.concatenate(keep) if keep else np.empty(0, dtype=int)
    if not len(selected):
        raise ValueError("no regional causal candidates")
    chosen = cls(
        tuple(catalogue.names[i] for i in selected),
        tuple(catalogue.satellite_numbers[i] for i in selected),
        tuple(catalogue.satellites[i] for i in selected),
    )
    p, v, good = v5_catalogue_memory.bounded_states(kernel.ecef_states, chosen, origin_utc_ns, grid)
    if not good.all():
        raise ValueError("causal state bank propagation failed")
    usage.update(
        coarse_catalogue=len(catalogue),
        selected=len(chosen),
        coarse_knots=len(coarse),
        fine_knots=len(grid),
        retained_state_bytes=p.nbytes + v.nbytes,
    )
    return dict(
        catalogue=chosen,
        source_indices=selected,
        bank=dict(
            time_s=grid,
            position_km=p,
            velocity_km_s=v,
            norad=np.array(chosen.satellite_numbers),
            phase_sigma_s=np.ones(len(chosen)),
        ),
    )


@contextmanager
def prepared_sky():
    from leo.analysis.localization_v3 import orbits

    from leo.operations import localization_v3_inputs

    usage = Counter()

    @wraps(localization_v3_inputs.regional_bank)
    def selected(*args, **kwargs):
        return regional_bank(orbits, usage, *args, **kwargs)

    with patch.object(localization_v3_inputs, "regional_bank", selected):
        yield usage


def worker(request, result, library):
    with prepared_sky() as usage:
        v5_armijo_aligned_finish.worker(request, result, library)
    path = Path(result)
    value = json.loads(path.read_bytes())
    value["boundary"] = BOUNDARY
    value["metrics"]["prep_stream_sky"] = dict(usage)
    save_json(path, value)


def run(case, work_dir):
    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    library = work_dir / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
