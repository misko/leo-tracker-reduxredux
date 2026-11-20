"""One blind center phase profile into the paired v5 cavity likelihood."""

import json
import sys
from functools import partial
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import (
    orbit_projector,
    portable_gate,
    v5_armijo_fit,
    v5_core,
    v5_lean,
    v5_shared_search,
)

METHOD = "bridge_cavity"
BOUNDARY = "Complete stored native GLRT through a detrended seed and the paired v5 cavity fit"
EARLY_ROUNDS = 2


class SeedUnavailable(ValueError):
    """The native profile supplies no acceptable seed for either arm."""


def detrended_profile(observed, frequency, slope, times, sigma, widths, period):
    """Rank physical curves after profiling out each track's unknown offset and rate."""
    dt = times - times.mean()
    power = float(dt @ dt)
    delta = observed[None, :] - frequency
    trend_free = []
    for values in (delta, slope):
        centered = values - values.mean(axis=1, keepdims=True)
        trend_free.append(centered - ((centered @ dt) / power)[:, None] * dt)
    y, h = trend_free
    phase = (y * h).sum(axis=1) / ((h * h).sum(axis=1) + (sigma / widths) ** 2)
    phase = np.clip(phase, -15, 15)
    residual = y - phase[:, None] * h
    square = (residual**2).sum(axis=1)
    return dict(
        cost=square / sigma**2 + (phase / widths) ** 2,
        rms_hz=np.sqrt(square / len(dt)),
        aliases=np.rint(-(delta - phase[:, None] * slope).mean(axis=1) / period).astype(int),
        phase_s=phase,
    )


def center_seed(scan, project, profile, zero_state):
    state = zero_state(scan)
    frequency, elevation, slope = project(scan.geometry, *scan.search_region.center)
    rows, aliases, keeps, phases = [], [], [], {}
    for i in scan.curved:
        track, ix = scan.tracks[i], scan.index[i]
        q = track["rf_hz"] / 11.5e9
        heights = elevation[:, ix]
        visible = np.flatnonzero(heights.min(axis=1) >= 0)
        j, alias, keep = 0, 0, False
        if len(visible):
            terms = profile(
                track["values"],
                q * frequency[:, ix][visible],
                q * slope[:, ix][visible],
                track["times"],
                scan.radio_sigma_hz,
                scan.sigma[visible],
            )
            k = int(np.argmin(terms["cost"]))
            j, alias = int(visible[k]), int(terms["aliases"][k])
            keep = bool(terms["rms_hz"][k] <= 450)
            if keep:
                phases.setdefault(j, []).append(float(terms["phase_s"][k]))
        rows.append(
            dict(
                component=track["key"],
                candidate_index=j,
                candidate_norad=int(scan.norads[j]),
                active_curvature=True,
            )
        )
        aliases.append(alias)
        keeps.append(np.full(len(track["times"]), keep))
    if not any(keep.any() for keep in keeps):
        raise SeedUnavailable("Center phase profile yielded no acceptable curved support")
    for j, values in phases.items():
        state["phases"][j] = np.median(values)
    return dict(seed=dict(rows=rows, state=state), aliases=aliases), np.concatenate(keeps)


def initialize(scan, metrics):
    from leo.analysis.localization_v3 import conservative_recovery, discovery
    from leo.analysis.localization_v3.families import AnchoredFamilies
    from leo.analysis.localization_v3.position import NormalPosition, fit

    from leo.analysis.research.retained_track_likelihood import PERIOD

    began = perf_counter()
    node, keep = center_seed(
        scan,
        discovery.phase_linear_frequency,
        partial(detrended_profile, period=PERIOD),
        discovery.zero_state,
    )
    p = NormalPosition(scan, node, scan.radio_sigma_hz, False, keep=keep)
    first = fit(p, np.zeros(2), iterations=24)
    anchor = np.asarray(first["parameters"])
    state = discovery.reference_state(p.state(anchor))
    trusted = {row["component"] for row, sl in zip(p.rows, p.slices, strict=True) if keep[sl].any()}
    with v5_shared_search.shared_associations(scan):
        seed, _ = discovery.explore(scan, state, anchor, "receiver_smooth")
    layout = AnchoredFamilies(scan, seed, "receiver_smooth", False, anchor)
    node = dict(seed=seed, aliases=layout.alias)
    keep = np.concatenate(
        [
            np.full(len(scan.tracks[i]["times"]), row["component"] in trusted)
            for row, i in zip(layout.rows, layout.members, strict=True)
        ]
    )
    p = NormalPosition(scan, node, scan.radio_sigma_hz, False, keep=keep)
    refined = fit(p, anchor, iterations=24)
    anchor = np.asarray(refined["parameters"])
    gates = conservative_recovery.retained_metrics(p, anchor)
    accepted = {r["component"] for r in gates["tracks"] if r["compatible"]}
    tracks = [
        dict(component=r["component"], compatible=r["component"] in accepted)
        for r in node["seed"]["rows"]
    ]
    metrics.update(
        start_xy=anchor.tolist(),
        first_xy=np.asarray(first["parameters"]).tolist(),
        profiled_tracks=len(tracks),
        phase_profile_points=int(keep.sum()),
        seed_gate_points=gates["accepted_points"],
        seed_gate_tracks=len(accepted),
        seed_gate_families=len(
            {r["candidate_index"] for r in node["seed"]["rows"] if r["component"] in accepted}
        ),
        center_seed_s=perf_counter() - began,
    )
    selected = dict(hypothesis=0, node=node, arms={"c0": {"metrics": {"tracks": tracks}}})
    return dict(choices=[selected], selected_hypothesis=0), 1


def worker(request, target, library):
    from leo.analysis.localization_v3 import conservative_recovery as recovery
    from leo.analysis.localization_v3 import position

    metrics = {}
    recover = recovery.conservative_recovery
    numerical_fit = recovery.fit_position
    infer = v5_core.infer

    def warm_fit(*args, **kwargs):
        return numerical_fit(*args, start=metrics["start_xy"], **kwargs)

    def retain(scan, initial, observations):
        with patch.object(recovery, "fit_position", warm_fit):
            result, skipped = portable_gate.retain_only(
                recovery,
                lambda: recover(scan, initial, observations, rounds=EARLY_ROUNDS, iterations=24),
            )
        metrics.update(early_retained=result["status"], **skipped)
        if result["status"] == "complete":
            metrics["retained_points"] = int(np.count_nonzero(result["final_mask"]))
        return result

    def bounded_infer(prepared, region, bound, stages, **kwargs):
        began = perf_counter()
        try:
            return infer(prepared, region, bound, stages, **kwargs)
        except SeedUnavailable as error:
            stages["initial"] = perf_counter() - began
            return dict(
                status="withheld",
                reason=str(error),
                boundary=BOUNDARY,
                arms={a: dict(latlon=None) for a in v5_lean.ARMS},
                metrics=dict(stage_s=stages),
            )

    warm = partial(initialize, metrics=metrics)
    with (
        patch.object(v5_core, "infer", bounded_infer),
        patch.object(position, "bounded_gauss_newton", v5_armijo_fit.bounded_armijo),
        patch.object(recovery, "conservative_recovery", retain),
    ):
        orbit_projector.worker(request, target, library, select_initial=warm)
    target = Path(target)
    result = json.loads(target.read_bytes())
    result["boundary"] = BOUNDARY
    result["metrics"]["center_bridge"] = metrics
    save_json(target, result)


def run(case, work_dir):
    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
