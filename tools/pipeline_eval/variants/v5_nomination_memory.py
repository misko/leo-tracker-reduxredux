"""Run complete-family coarse nomination in ordered orbit row tiles."""

import json
import sys
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import orbit_projector, v5_lean, v5_signed_context_memory

METHOD = "v5_nomination_memory"
BOUNDARY = "Complete compact v5 with ordered row-bounded family nomination"
TILE = 64


def screen(family, sky, coordinates, means, widths, data, observe=None):
    n = len(means)
    out = {}
    minimum = np.empty(n)
    radio = data["radio"] @ data["coefficient"][: data["radio_width"]]
    knots = sky["time_s"]
    payload = 0
    for start in range(0, n, TILE):
        part = slice(start, min(n, start + TILE))
        bank = dict(
            time_s=knots,
            position_km=sky["position_km"][part],
            velocity_km_s=sky["velocity_km_s"][part],
        )
        phases = means[part]
        f, e = family.phase_frequency_grid(bank, data["times"], *coordinates, phase_seconds=phases)
        minimum[part] = e.min(axis=1)
        block_bytes = f.nbytes + e.nbytes
        del e
        plus, elevation = family.phase_frequency_grid(
            bank, data["times"], *coordinates, phase_seconds=phases + 0.01
        )
        block_bytes = max(block_bytes, f.nbytes + plus.nbytes + elevation.nbytes)
        del elevation
        minus, elevation = family.phase_frequency_grid(
            bank, data["times"], *coordinates, phase_seconds=phases - 0.01
        )
        payload = max(
            payload, block_bytes, f.nbytes + plus.nbytes + minus.nbytes + elevation.nbytes
        )
        del elevation
        score = family.coarse_phase_scores(
            data["values"],
            radio,
            f * data["q"],
            (plus - minus) / 0.02 * data["q"],
            widths[part],
            data["base_covariance"],
            data["groups"],
        )
        for name, value in score.items():
            if name not in out:
                out[name] = np.empty((n, *value.shape[1:]), dtype=value.dtype)
            out[name][part] = value
        del f, plus, minus
    scores = np.where(minimum >= 0, out["score"], np.inf)
    if observe is not None:
        observe(out, minimum, payload)
    return scores, out["aliases"]


def nominate(family, d, observe=None, trace=None):
    """Use the original family policies around a bounded coarse score inventory."""
    case, scan, base = d["case"], d["scan"], d["base"]
    try:
        rows = []
        targets = sorted(
            {
                r["candidate_index"]
                for r, sl in zip(base.rows, base.slices, strict=True)
                if d["keep"][sl].any()
            }
        )
        for target in targets:
            if trace is not None:
                trace("enter", "family_data", target)
            data = family.family_data(d, target)
            if trace is not None:
                trace("leave", "family_data", target)
            data["target"] = target
            if len(data["values"]) < 4:
                continue
            if trace is not None:
                trace("enter", "coarse", target)
            scores, aliases = screen(
                family,
                scan.sky,
                scan.search_region.latlon(d["x"]),
                d["all_means"],
                d["widths"],
                data,
                observe,
            )
            if trace is not None:
                trace("leave", "coarse", target)
            ordered = [
                int(j) for j in np.argsort(scores) if np.isfinite(scores[j]) and j != target
            ][:7]
            if trace is not None:
                trace("enter", "refine", target)
            candidates = [
                family.candidate_prediction(d, data, j, aliases[j]) for j in [target] + ordered
            ]
            if trace is not None:
                trace("leave", "refine", target)
            eligible = sorted((r for r in candidates if r["qualified"]), key=lambda r: r["score"])
            original = candidates[0]
            best = next((r for r in eligible if r["candidate_index"] != target), None)
            gain = original["score"] - best["score"] if best is not None else None
            rows.append(
                dict(
                    original_index=target,
                    original_norad=int(scan.norads[target]),
                    members=data["members"],
                    held_observation_ids=data["held_ids"],
                    held_points=len(data["values"]),
                    coarse_candidate_count=len(scores),
                    candidates=candidates,
                    original=original,
                    best=best,
                    predictive_gain=gain,
                    search_penalty=float(2 * np.log(len(scores))),
                    all_held_points_disjoint_from_calibration=True,
                    cavity_phase_change_s=data["cavity_phase_change_s"],
                    no_predictive_noise_gate_used_to_veto_a_joint_proposal=True,
                )
            )
        return dict(
            case=case,
            status="complete",
            families=rows,
            reference_position_used=False,
            no_RF_GPS_future_TLE_or_point_deletion=True,
            incumbent_arms=d["signed"]["policy_arms"],
        )
    except Exception as exc:
        return dict(case=case, status="failed", error=repr(exc))


@contextmanager
def nomination_memory(observe=None, trace=None):
    from leo.analysis.localization_v3 import family_cavity

    with patch.object(
        family_cavity,
        "nominate_families",
        partial(nominate, family_cavity, observe=observe, trace=trace),
    ):
        yield


def worker(request, result, library):
    with nomination_memory():
        v5_signed_context_memory.worker(request, result, library)
    path = Path(result)
    value = json.loads(path.read_bytes())
    value["boundary"] = BOUNDARY
    save_json(path, value)


def run(case, work_dir):
    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
