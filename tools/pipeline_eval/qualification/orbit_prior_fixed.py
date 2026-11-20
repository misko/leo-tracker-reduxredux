"""Fit paired phase-width arms from one sanitized fixed-owner packet."""

from time import perf_counter, process_time

import numpy as np

from ..scoring import ARMS
from ..variants import orbit_prior, robust_em, robust_orbit_fit
from . import owner_factor_models as model


def refit(packet, rows, prior, order):
    tile, region, index = model.bank(packet)
    used = [row for row in rows if row["v5_owner"] in index and row["lean_owner"] in index]
    if not used:
        return dict(status="unavailable", reason="no common owner inside the causal tile bank")
    half = float(packet["offer"].get("width_km", 25)) / 2
    groups = model.fragments(used, "lean", "lean", index)
    names = sorted({str(group.norad) for group in groups})
    sigmas = np.full(len(index), robust_em.PHASE_SD_S)
    for name in names:
        sigmas[index[int(name)]] = prior[name]["width_s"]
    methods = {}
    for method in order:
        wall, cpu = perf_counter(), process_time()
        fitted = {}
        for arm in ARMS:
            args = (groups, tile, region, half, arm)
            xy, phases, radio, objective, stage = (
                model._least_fit(*args)
                if method == "equal"
                else orbit_prior.fixed_fit(model._least_fit, sigmas, *args)
            )
            site, latlon = region.site(xy)
            residual = np.concatenate(
                [
                    g.y
                    - robust_orbit_fit.project(tile, g.orbit, g.t, site, phase, g.rf)[0]
                    - correction
                    for g, phase, correction in zip(groups, phases, radio, strict=True)
                ]
            )
            fitted[arm] = dict(
                latlon=None,
                forced_latlon=latlon,
                rf_rms_hz=float(np.sqrt(np.mean(residual**2))),
                objective=objective,
                points=len(used),
                phase_s=dict(zip((str(g.norad) for g in groups), map(float, phases), strict=True)),
                **stage,
            )
        methods[method] = dict(
            arms=fitted, fit_wall_s=perf_counter() - wall, fit_cpu_s=process_time() - cpu
        )
    return dict(
        status="ok",
        outside_tile_causal_bank=len(rows) - len(used),
        orbit_names=names,
        rows=len(used),
        groups=len(groups),
        methods=methods,
    )
