"""Keep only tiled coarse phase profiles and whole-roster scalar scores."""

import copy
import json
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import history_stream_prep, orbit_projector, v5_lean

METHOD = "v5_tiled_salvage"
BOUNDARY = "Complete aligned compact v5 with bounded in-memory conservative salvage phases"
ROWS = 16


def coarse_scores(profile, measured, noise, f, elevation, derivative, q, phases, mask, counters):
    """Tile complete contiguous candidate rows, retaining only their minimum costs."""
    columns = len(measured) if mask is None else int(mask.sum())
    y, sigma = (measured, noise) if mask is None else (measured[mask], noise[mask])
    inverse = np.diag(1 / sigma)
    scores = np.empty(len(f))
    for i in range(0, len(f), ROWS):
        rows = slice(i, i + ROWS)
        prediction = q * (f[rows, None] + derivative[rows, None] * phases[None, :, None])
        e = elevation[rows]
        if mask is not None:
            prediction = prediction[:, :, mask]
            e = e[:, mask]
        terms = profile(y, prediction.reshape(-1, columns), inverse)
        cost = terms["cost"].reshape(len(e), -1) + phases[None, :] ** 2 / 9
        cost[e.max(axis=1) < 0] = np.inf
        scores[rows] = cost.min(axis=1)
        counters["tiles"] += 1
        counters["max_prediction_bytes"] = max(counters["max_prediction_bytes"], prediction.nbytes)
        counters["max_profile_output_bytes"] = max(
            counters["max_profile_output_bytes"], sum(v.nbytes for v in terms.values())
        )
        del prediction, terms, cost
    counters["coarse_windows"] += 1
    return scores


def fine_alternatives(kernel, scan, track, y, noise, rf, shortlist, coordinates):
    """Keep the frozen fine support grid and per-support publication gates."""
    t, values = track["times"], track["values"]
    grid = np.linspace(-15, 15, 121)
    supports = [
        (a, b)
        for a, b in kernel.selected_supports(len(t))
        if t[b - 1] - t[a] >= 20 and kernel.raw_curvature(dict(times=t[a:b], values=values[a:b]))
    ]
    alternatives = []
    for j in sorted(shortlist):
        bank = dict(
            time_s=scan.sky["time_s"],
            position_km=np.repeat(scan.sky["position_km"][[j]], len(grid), axis=0),
            velocity_km_s=np.repeat(scan.sky["velocity_km_s"][[j]], len(grid), axis=0),
        )
        f, e = kernel.paired_phase_frequency(
            bank, np.tile(t, len(grid)), np.repeat(np.arange(len(grid)), len(t)), grid, *coordinates
        )
        f, e = f.reshape(len(grid), -1), e.reshape(len(grid), -1)
        for a, b in supports:
            terms = kernel.profile(y[a:b], rf * f[:, a:b], np.diag(1 / noise[a:b]))
            cost = terms["cost"] + grid**2 / 9
            cost[e[:, a:b].min(axis=1) < 0] = np.inf
            best = int(np.argmin(cost))
            residual = terms["residual"][best]
            screen = kernel.batch_noise_screen(residual[None], t[a:b])
            max_sigma = np.max(abs(residual) / noise[a:b])
            if (
                terms["rms"][best] > 450
                or abs(terms["bias"][best]) > 3000
                or not np.isfinite(cost[best])
                or not screen["noise_screen_pass"][0]
                or max_sigma > 6
            ):
                continue
            alternatives.append(
                dict(
                    start_index=a,
                    stop_index=b,
                    points=b - a,
                    candidate_index=j,
                    norad=int(scan.norads[j]),
                    phase_s=float(grid[best]),
                    cost=float(cost[best]),
                    alias=int(terms["alias"][best]),
                    rms_hz=float(terms["rms"][best]),
                    max_external_radio_sigma=float(max_sigma),
                )
            )
    alternatives.sort(key=lambda row: (-row["points"], row["cost"]))
    return alternatives[:5], len(supports)


def salvage(kernel, counters, trace, scan, node, keep, *, rounds=5, iterations=48):
    p, fitted, _, _ = kernel.repaired_fit(
        scan, node, "c0", "unit", keep, rounds=rounds, iterations=iterations
    )
    x = fitted["parameters"]
    state = p.state(x)
    coordinates = scan.search_region.latlon(x)
    repaired, retained, diagnostics = copy.deepcopy(node), keep.copy(), []
    phases = np.linspace(-10, 10, 81)
    for k, (i, sl) in enumerate(zip(p.members, p.slices, strict=True)):
        if keep[sl].any():
            continue
        track = scan.tracks[i]
        t, values = track["times"], track["values"]
        q = track["rf_hz"] / 11500000000.0
        radio = scan.hardware(track, state["beta"])
        radio += q * scan.rx_basis[i] @ state["smooth"][track["receiver"] - 1]
        y, noise = values - radio, p.point_noise[sl]
        f, elevation, derivative = kernel.phase_linear_frequency(
            kernel.prepare_phase_geometry(scan.sky, t), *coordinates
        )
        score = coarse_scores(
            kernel.profile, y, noise, f, elevation, derivative, q, phases, None, counters
        )
        shortlist = set(map(int, np.argsort(score)[:30]))
        for lo in np.arange(t[0], t[-1], 20):
            mask = (t >= lo) & (t < lo + 20)
            if mask.sum() >= 8:
                score = coarse_scores(
                    kernel.profile, y, noise, f, elevation, derivative, q, phases, mask, counters
                )
                shortlist.update(map(int, np.argsort(score)[:10]))
        shortlist.add(p.rows[k]["candidate_index"])
        alternatives, supports = fine_alternatives(
            kernel, scan, track, y, noise, q, shortlist, coordinates
        )
        chosen = alternatives[0] if alternatives else None
        diagnostics.append(
            dict(
                component=track["key"],
                candidate_count=len(shortlist),
                supports_tested=supports,
                selected=chosen,
                alternatives=alternatives,
            )
        )
        trace.append(dict(component=track["key"], candidate_indices=sorted(shortlist)))
        if chosen:
            repaired["seed"]["rows"][k].update(
                candidate_index=chosen["candidate_index"], candidate_norad=chosen["norad"]
            )
            repaired["aliases"][k] = chosen["alias"]
            retained[sl.start + chosen["start_index"] : sl.start + chosen["stop_index"]] = True
    return repaired, retained, diagnostics


@contextmanager
def tiled_salvage():
    from leo.analysis.localization_v3 import conservative_recovery

    counters, trace = Counter(), []

    def replace(*args, **kwargs):
        return salvage(conservative_recovery, counters, trace, *args, **kwargs)

    with patch.object(conservative_recovery, "salvage", replace):
        yield counters, trace


def worker(request, result, library):
    with tiled_salvage() as (counts, trace):
        history_stream_prep.worker(request, result, library)
    path = Path(result)
    value = json.loads(path.read_bytes())
    value["boundary"] = BOUNDARY
    value["metrics"]["tiled_salvage"] = dict(counters=dict(counts), shortlists=trace)
    save_json(path, value)


def run(case, work_dir):
    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    library = work_dir / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
