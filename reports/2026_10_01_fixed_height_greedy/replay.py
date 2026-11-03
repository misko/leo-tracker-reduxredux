"""Independent, source-bound fixed-MSL-height scan replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.append(str(HERE.parent / "2026_09_30_broad_prior_acquisition"))
from common import load_scan, digest, seal, source_bindings
from prior import build_uniform_prior, prior_description
from leo.analysis.gaussian_sum_location import (
    GaussianComponent, FilterState, FilterConfig, update_filter,
)


def reduced_prior(layout):
    keep = np.r_[0, 1, np.arange(3, layout.dimension)]
    return FilterState(tuple(
        GaussianComponent(c.weight, c.mean[keep], c.covariance[np.ix_(keep, keep)])
        for c in build_uniform_prior(layout).components))


def components(state):
    return [{"weight":c.weight, "mean":c.mean[:5].tolist(),
             "horizontal_covariance":c.covariance[:2,:2].tolist(),
             "identity_history":list(c.identity_history),
             "max_abs_satellite_epoch_s":float(np.max(np.abs(c.mean[5:]),initial=0.))}
            for c in state.components]


def support_failures(state, radius=489.):
    failures = set()
    for c in state.components:
        if np.linalg.norm(c.mean[:2]) > 250.:
            failures.add("uniform_region_center_boundary")
        if np.linalg.norm(c.mean[:2]) + 5*np.sqrt(np.linalg.eigvalsh(c.covariance[:2,:2])[-1]) > radius:
            failures.add("position_support_boundary")
    return sorted(failures)


def replay(unit, output, width=1, max_tracks=None, extended=False):
    from geoid import load_height_model
    from physics_fixed import build_fixed_height_factor
    started = time.monotonic()
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    scan = load_scan(unit)
    if extended:
        from orbit_input import use_extended_orbits
        scan = use_extended_orbits(scan)
    height = load_height_model()
    state = reduced_prior(scan.layout)
    sources = [HERE / p for p in ("replay.py", "physics_fixed.py", "geoid.py", "PROTOCOL.md", "orbit_input.py")]
    receipt = {"schema":"fixed-msl-greedy-replay/v1", "unit_id":unit,
        "arm":f"fixed_height_beam{width}", "status":"running",
        "source_sha256":source_bindings(sources), "inputs":scan.inputs,
        "height_input_bindings":height.input_bindings,
        "height_msl_m":30.48, "spatial_prior":prior_description(),
        "extended_causal_orbits":extended,
        "state_layout":"east_km,north_km,clock_s,rx0_drift,rx1_drift,satellite_epochs",
        "initial_components":components(state), "planned_factors":len(scan.tracks),
        "exclusions":scan.exclusions, "candidate_count":len(scan.bank.norad_ids),
        "checkpoints":[], "gate_failures":[],
        "qualification":"greedy/beam search; retained weights are not calibrated posterior probabilities"}
    selected = scan.tracks if max_tracks is None else scan.tracks[:max_tracks]
    try:
        for track_id, obs in selected:
            if time.monotonic()-started > 85:
                receipt["status"] = "budget_reached"
                break
            factor = build_fixed_height_factor(obs, scan.bank, scan.layout, scan.config, height).factor
            result = update_filter(state, factor, FilterConfig(max_components=width,
                greedy=width==1, min_weight=1e-12, max_child_work=65536))
            state = result.state
            failures = support_failures(state,scan.config.support_radius_km)
            if "ineligible_positive_prior_mass" in result.flags:
                failures.append("source_prior_mass_missing")
            receipt["checkpoints"].append({"track_id":track_id,
                "observation_ids":list(factor.observation_ids),
                "retained_mass":result.retained_pre_normalization_mass,
                "background_probability":result.background_probability,
                "predictive_log_density":result.predictive_log_density,
                "components":components(state), "gate_failures":failures,
                "seconds":time.monotonic()-started})
            receipt["gate_failures"].extend(failures)
            output.parent.mkdir(parents=True,exist_ok=True)
            output.with_suffix(".progress.json").write_text(json.dumps(receipt,allow_nan=False))
            if failures:
                receipt["status"] = "gate_failed"
                break
        else:
            receipt["status"] = "complete" if len(selected)==len(scan.tracks) else "prefix_only"
    except Exception as error:
        receipt["status"] = "error"
        receipt["exception"] = {"type":type(error).__name__,"message":str(error)}
    receipt["components"] = components(state)
    receipt["consumed_observation_ids"] = list(state.consumed_observation_ids)
    receipt["gate_failures"] = sorted(set(receipt["gate_failures"]))
    receipt["wall_seconds"] = time.monotonic()-started
    seal(output,receipt)
    print(json.dumps({k:receipt[k] for k in ("unit_id","status","gate_failures","wall_seconds")}))


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("unit")
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--width",type=int,default=1)
    p.add_argument("--max-tracks",type=int)
    p.add_argument("--extended",action="store_true")
    a=p.parse_args()
    replay(a.unit,a.output,a.width,a.max_tracks,a.extended)
