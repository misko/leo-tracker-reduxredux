"""Prepare strict-causal orbit-phase states and fit the formal orbit model."""

import argparse
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

import numpy as np
from replay_regional_doppler import state_arrays

from leo.analysis.research.formal_orbit import FormalOrbitConfig, FormalOrbitData, fit_formal_orbit
from leo.analysis.research.regional_doppler import Region
from leo.sky.propagation import parse_element_sets


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_strict_phase_states(
    z,
    assignments,
    targets,
    strict_rows,
    phase_step_s=1.0,
    propagate=state_arrays,
    expected_sources=446,
    parse_catalogue=parse_element_sets,
):
    """Build nominal and phase-shifted states without reusing clock shifts."""
    lookup = {(r["session_id"], r["episode_id"]): r for r in strict_rows}
    if len(assignments) != len(targets):
        raise ValueError("assignment/phase-target count mismatch")
    arrays = {
        k: np.empty_like(z["p"] if "p" in k else z["v"])
        for k in ("p", "v", "phase_p_minus", "phase_v_minus", "phase_p_plus", "phase_v_plus")
    }
    source = np.empty(len(z["y"]), np.int64)
    age = np.empty(len(z["y"]), float)
    for episode, (assignment, target) in enumerate(zip(assignments, targets, strict=True)):
        identity = (assignment["session_id"], assignment["episode_id"])
        if identity != (target["session_id"], target["episode_id"]):
            raise ValueError("phase-target ordering mismatch")
        row = lookup.get(identity)
        if row is None:
            raise ValueError("assignment missing from strict causal reranking")
        if int(row["best_norad"]) != int(target["norad"]):
            raise ValueError("strict NORAD mismatch")
        if row["winning_epoch_utc_ns"] >= row["capture_start_utc_ns"]:
            raise ValueError("noncausal TLE")
        if row.get("winning_collected_utc_ns") is None:
            raise ValueError("missing TLE availability evidence")
        if row["winning_collected_utc_ns"] >= row["capture_start_utc_ns"]:
            raise ValueError("late TLE availability")
        mask = np.asarray(z["episode"]) == episode
        source[mask] = int(row["best_norad"])
        age[mask] = (row["capture_start_utc_ns"] - row["winning_epoch_utc_ns"]) / 3_600_000_000_000
        catalogue = parse_catalogue(row["winning_tle_text"])
        mean = float(target["predicted_phase_s"])
        for suffix, shift in (("", 0.0), ("_minus", -phase_step_s), ("_plus", phase_step_s)):
            p, v, valid = propagate(
                catalogue,
                [0],
                row["capture_start_utc_ns"],
                z["time"][mask],
                orbit_time_s=mean + shift,
                clock_s=0.0,
            )
            if len(valid) != 1:
                raise ValueError("invalid strict phase propagation")
            arrays["p" if not suffix else "phase_p" + suffix][mask] = p[0]
            arrays["v" if not suffix else "phase_v" + suffix][mask] = v[0]
    if expected_sources is not None and len(np.unique(source)) != expected_sources:
        raise ValueError(f"strict population must contain {expected_sources} NORADs")
    return arrays, source, age


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in (
        "states",
        "parent-inference",
        "prior-analysis",
        "strict-reranking",
        "strict-inference",
        "output",
    ):
        p.add_argument("--" + key, required=True, type=Path)
    p.add_argument("--region", required=True)
    p.add_argument("--initial", default="[0,0]")
    p.add_argument("--prepared-output", type=Path)
    a = p.parse_args()
    z = np.load(a.states)
    parent = json.loads(a.parent_inference.read_text())
    prior = json.loads(a.prior_analysis.read_text())
    strict = json.loads(a.strict_reranking.read_text())
    strict_inference = json.loads(a.strict_inference.read_text())
    if not strict.get("strictly_causal") or strict.get("evaluation_location_used"):
        raise ValueError("reranking is not causal/location-blind")
    if prior["causal_digest"] != digest(a.strict_inference):
        raise ValueError("prior/strict digest mismatch")
    if strict_inference["rerank_digest"] != digest(a.strict_reranking):
        raise ValueError("rerank digest mismatch")
    if strict_inference["states_digest"] != digest(a.states):
        raise ValueError("states digest mismatch")
    arrays, source, age = prepare_strict_phase_states(
        z, parent["assignments"], prior["targets"], strict["rows"]
    )
    ids = z["observation_id"] if "observation_id" in z else np.arange(len(z["y"]))
    data = FormalOrbitData(
        z["y"],
        z["training"].astype(bool),
        z["segment"],
        z["episode"],
        source,
        age,
        arrays["p"],
        arrays["v"],
        arrays["phase_p_minus"],
        arrays["phase_v_minus"],
        arrays["phase_p_plus"],
        arrays["phase_v_plus"],
        z["time"],
        ids,
    )
    config = FormalOrbitConfig()
    if a.prepared_output:
        np.savez_compressed(
            a.prepared_output,
            schema=np.asarray("formal-orbit-phase-state-v1"),
            **data.__dict__,
            strict_reranking_digest=np.asarray(digest(a.strict_reranking)),
            prior_analysis_digest=np.asarray(digest(a.prior_analysis)),
        )
    result = fit_formal_orbit(data, Region(**json.loads(a.region)), json.loads(a.initial), config)
    payload = {
        "schema": "org.leo.research.formal-fixed-orbit/v1",
        "configuration": asdict(config),
        "result": asdict(result),
        "truth_used": False,
        "heldout_used_to_fit": False,
        "inputs": {
            k: digest(getattr(a, k))
            for k in (
                "states",
                "parent_inference",
                "prior_analysis",
                "strict_reranking",
                "strict_inference",
            )
        },
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.output.with_suffix(a.output.suffix + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(a.output)


if __name__ == "__main__":
    main()
