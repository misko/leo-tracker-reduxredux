"""Alternate full retained catalogue assignment with scan-shared epoch fitting."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def select_scan(single, arrays, evidence, point, tau):
    selected, objective_rows = [], []
    for source in evidence:
        times = np.asarray(source["times_s"], dtype=float)
        if np.ptp(times) < 3.0:
            continue
        pos, vel = single.interpolate_track(
            arrays["position_ecef_km"],
            arrays["velocity_ecef_km_s"],
            arrays["receive_plus_tau_offset_ns"],
            times + tau,
        )
        base = {
            "track_id": source["track_id"],
            "times_s": times,
            "measured_hz": np.asarray(source["measured_hz"], dtype=float),
            "training_mask": np.asarray(source["training_mask"], dtype=bool),
            "weight_s": int(len(np.unique(np.floor(times)))),
        }
        _, rows = single.score_point(
            [{**base, "position": pos, "velocity": vel}],
            arrays["candidate_id"],
            *point,
        )
        winner = rows[0]
        if winner["candidate_id"] is None:
            raise ValueError("no visible candidate; do not silently drop track")
        index = np.flatnonzero(arrays["candidate_id"].astype(str) == winner["candidate_id"])
        if len(index) != 1:
            raise ValueError("candidate IDs must be unique")
        selected.append(
            {
                **base,
                "candidate_id": winner["candidate_id"],
                "grid_ns": arrays["receive_plus_tau_offset_ns"],
                "position": arrays["position_ecef_km"][index[0]].copy(),
                "velocity": arrays["velocity_ecef_km_s"][index[0]].copy(),
            }
        )
        objective_rows.append(winner)
    return selected, objective_rows


def reassociate(single, root, sessions, point, taus):
    tracks = []
    for sid in sessions:
        receipt = json.loads((root / sid / "cache_receipt.json").read_text())
        if receipt["session_id"] != sid:
            raise ValueError("cache session mismatch")
        with np.load(root / sid / "state_cache.npz", allow_pickle=False) as archive:
            arrays = {key: archive[key] for key in archive.files}
        chosen, _ = select_scan(
            single, arrays, receipt["prepared_evidence"]["tracks"], point, taus[sid]
        )
        tracks.extend({**track, "session_id": sid} for track in chosen)
    return tracks


def identities(rows):
    return {(row["session_id"], row["track_id"]): row["candidate_id"] for row in rows}


def outer_stop_reason(cycle, changes, gain):
    if changes == 0 and gain < 0.001:
        return "stable_identities_small_gain"
    return "cycle_limit" if cycle >= 10 else None


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output required")
    helper = load(args.helper, "joint_epoch_helper")
    single = load(args.single, "joint_epoch_single")
    source = json.loads(args.inference.read_text())
    if (
        source["schema"] != "conditional-full8h-shared-epoch-position/v1"
        or source["position_truth_used"]
        or source["reserved_rows_used"]
    ):
        raise ValueError("conditional inference is not the required training-only schema")
    if (
        digest(args.inference).removeprefix("sha256:")
        != args.inference.with_suffix(".sha256").read_text().strip()
    ):
        raise ValueError("conditional inference seal mismatch")
    if source["bindings"]["tool"] != digest(args.helper):
        raise ValueError("conditional numerical source mismatch")
    if source["bindings"]["single_tool"] != digest(args.single):
        raise ValueError("prediction source mismatch")
    expected_arms = {
        (prior, scale) for prior in ("sacramento", "reno") for scale in (0.2, 1.0, 5.0)
    }
    if (
        len(source["arms"]) != 6
        or {(arm["prior"], arm["scale_s"]) for arm in source["arms"]} != expected_arms
    ):
        raise ValueError("expected all six frozen arms")
    manifest = json.loads(args.manifest.read_text())
    sessions = manifest["partitions"]["train"]["session_ids"][:72]
    if source["session_ids"] != sessions or len(set(sessions)) != 72:
        raise ValueError("not the frozen full first TRAIN group")
    if [row["session_id"] for row in source["bindings"]["caches"]] != sessions:
        raise ValueError("incomplete or out-of-order cache bindings")
    for binding in source["bindings"]["caches"]:
        folder = args.cache_root / binding["session_id"]
        if (
            digest(folder / "cache_receipt.json") != binding["receipt"]
            or digest(folder / "state_cache.npz") != binding["cache"]
        ):
            raise ValueError("cache digest mismatch")
    started = time.monotonic()
    arms = []
    for arm in source["arms"]:
        prior = single.PRIORS[arm["prior"]]
        position = np.array([arm["east_km"], arm["north_km"]])
        taus = dict(arm["taus_s"])
        previous_ids = identities(arm["fixed_tracks"])
        previous_objective = arm["penalized_objective_rmse_hz"]
        trace = []
        for cycle in range(1, 11):
            point = single.offset_coordinate(prior[:2], *position)
            tracks = reassociate(single, args.cache_root, sessions, point, taus)
            new_ids = identities(tracks)
            if new_ids.keys() != previous_ids.keys():
                raise ValueError("reassignment changed track support")
            changes = sum(new_ids[key] != previous_ids[key] for key in new_ids)
            reassigned = helper.score(single, tracks, point, taus, arm["scale_s"])
            if reassigned["penalized_objective_rmse_hz"] > previous_objective + 1e-7:
                raise ValueError("full catalogue reassignment increased objective")
            proposal, tau_proposal, polish, stopped, reason = helper.coupled_polish(
                single,
                tracks,
                prior,
                position.copy(),
                dict(taus),
                arm["scale_s"],
            )
            scored = helper.score(
                single,
                tracks,
                single.offset_coordinate(prior[:2], *proposal),
                tau_proposal,
                arm["scale_s"],
            )
            accepted = (
                scored["penalized_objective_rmse_hz"]
                <= reassigned["penalized_objective_rmse_hz"] + 1e-9
            )
            if accepted:
                position, taus = proposal, tau_proposal
            else:
                scored = reassigned
            gain = previous_objective - scored["penalized_objective_rmse_hz"]
            trace.append(
                {
                    "cycle": cycle,
                    "identity_changes": changes,
                    "objective_before_hz": previous_objective,
                    "objective_after_reassignment_hz": reassigned["penalized_objective_rmse_hz"],
                    "objective_after_polish_hz": scored["penalized_objective_rmse_hz"],
                    "polish_accepted": accepted,
                    "polish_stopping_rule_satisfied": stopped,
                    "polish_reason": reason,
                    "polish_trace": polish,
                    "objective_gain_hz": gain,
                }
            )
            previous_ids, previous_objective = new_ids, scored["penalized_objective_rmse_hz"]
            stop_reason = outer_stop_reason(cycle, changes, gain)
            if stop_reason is not None:
                break
        point = single.offset_coordinate(prior[:2], *position)
        arms.append(
            {
                "prior": arm["prior"],
                "scale_s": arm["scale_s"],
                "latitude_deg": point[0],
                "longitude_deg": point[1],
                "east_km": float(position[0]),
                "north_km": float(position[1]),
                "taus_s": taus,
                "trace": trace,
                "outer_stop_reason": stop_reason,
                "outer_stopping_rule_satisfied": stop_reason == "stable_identities_small_gain",
                "fixed_tracks": scored["rows"],
                **{key: value for key, value in scored.items() if key != "rows"},
            }
        )
    payload = {
        "schema": "long-joint-epoch-association/v1",
        "position_truth_used": False,
        "reserved_rows_used": False,
        "numerical_monotonicity_tolerances_hz": {"reassignment": 1e-7, "polish": 1e-9},
        "session_ids": sessions,
        "arms": arms,
        "runtime_s": time.monotonic() - started,
        "bindings": {
            "conditional_inference": digest(args.inference),
            "helper": digest(args.helper),
            "single": digest(args.single),
            "manifest": digest(args.manifest),
            "tool": digest(__file__),
            "protocol": digest(Path(__file__).with_name("PROTOCOL.md")),
        },
    }
    args.output.mkdir(parents=True)
    raw = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    (args.output / "inference.json").write_text(raw)
    (args.output / "inference.sha256").write_text(hashlib.sha256(raw.encode()).hexdigest() + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inference", "helper", "single", "manifest", "cache-root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
