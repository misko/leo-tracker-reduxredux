#!/usr/bin/env python3
"""Score RF-authorized receiver pairs with a soft shared-identity latent state."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

from leo.analysis.research.paired_receiver_geometry import (
    PairedDopplerFactor,
    score_paired_doppler_factor,
)
from leo.analysis.research.regional_doppler import (
    LIGHT_KM_S,
    REFERENCE_RF_HZ,
    ObservationArc,
    Region,
    ScoreConfig,
    logsumexp,
)
from leo.sky.propagation import parse_element_sets

Q_ARMS = (0.5, 0.9, 0.99)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def content_digest(document: dict) -> str:
    body = dict(document)
    claimed = body.pop("content_digest", None)
    actual = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    if claimed != actual:
        raise ValueError("content digest mismatch")
    return actual


def mixed_log_evidence(independent: float, shared: float, q: float) -> float:
    """Marginalize the shared-source state against an independent/outlier state."""
    if not 0 < q < 1 or not np.all(np.isfinite((independent, shared))):
        raise ValueError("finite evidences and open-interval q required")
    return float(np.logaddexp(np.log1p(-q) + independent, np.log(q) + shared))


def component_log_evidence(
    candidate_train: np.ndarray,
    candidate_heldout: np.ndarray,
    null_train: float,
    null_heldout: float,
    catalogue_size: int,
    signal_prior: float,
) -> tuple[float, float]:
    """Return train and joint evidence with one full-population signal prior."""
    train = np.asarray(candidate_train, dtype=float)
    heldout = np.asarray(candidate_heldout, dtype=float)
    if train.shape != heldout.shape or train.ndim != 1 or not len(train):
        raise ValueError("candidate likelihood arrays must be aligned vectors")
    if catalogue_size < len(train) or not 0 < signal_prior < 1:
        raise ValueError("full catalogue size and signal prior are invalid")
    log_prior = np.log(signal_prior / catalogue_size)
    null_prior = np.log1p(-signal_prior)
    training = float(np.logaddexp(logsumexp(train + log_prior), null_train + null_prior))
    joint = float(
        np.logaddexp(
            logsumexp(train + heldout + log_prior),
            null_train + null_heldout + null_prior,
        )
    )
    return training, joint


def _load_replay():
    path = Path(__file__).parents[1] / "replay_regional_doppler.py"
    spec = importlib.util.spec_from_file_location("soft_pair_replay", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("replay loader unavailable")
    spec.loader.exec_module(module)
    return module, path


def _visit_map(authority: dict) -> dict[str, int]:
    output = {}
    for row in authority["rf_detection_table"]:
        key, visit = row["source_group_id"], int(row["visit"])
        if key in output and output[key] != visit:
            raise ValueError("one source group maps to multiple visits")
        output[key] = visit
    return output


def shared_five_block_partition(
    left: dict, right: dict, excluded_left: set[str], excluded_right: set[str], visits: dict
) -> dict[int, bool]:
    """Assign whole common-clock visits to five alternating blocks."""
    left_visits = [visits[x] for x in left["paired_visit_ids"] if x not in excluded_left]
    right_visits = [visits[x] for x in right["paired_visit_ids"] if x not in excluded_right]
    ordered = np.asarray(sorted(set(left_visits + right_visits)), dtype=int)
    if len(ordered) < 5:
        raise ValueError("too few visits after authority-anchor exclusion")
    training_visits = set(
        int(value)
        for index, block in enumerate(np.array_split(ordered, 5))
        if index in (0, 2, 4)
        for value in block
    )
    result = {int(value): int(value) in training_visits for value in ordered}
    for lane in (left_visits, right_visits):
        counts = (sum(result[x] for x in lane), sum(not result[x] for x in lane))
        if min(counts) < 2:
            raise ValueError("shared five-block split lacks path support")
    return result


def _arc(row: dict, excluded: set[str], partition: dict[int, bool], visits: dict):
    keep = np.asarray([value not in excluded for value in row["paired_visit_ids"]])
    groups = np.asarray(row["paired_visit_ids"])[keep]
    visit = np.asarray([visits[value] for value in groups])
    return ObservationArc(
        time_s=np.asarray(row["t_s"], dtype=float)[keep],
        frequency_hz=np.asarray(row["y_hz"], dtype=float)[keep],
        segment=np.asarray([row["tracklet_id"]] * int(np.sum(keep))),
        training=np.asarray([partition[int(value)] for value in visit], dtype=bool),
        partition="randomized",
    ), visit


def _prediction(position, velocity, receiver):
    delta = position[None] - receiver.ecef_km[:, None, None]
    distance = np.linalg.norm(delta, axis=-1)
    prediction = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * velocity[None], axis=-1) / distance
    elevation = np.sum(delta * receiver.up[:, None, None], axis=-1) / distance
    return prediction, elevation


def _factor_evidence(factor, prediction, visible, population, config, effective_count):
    flat = score_paired_doppler_factor(
        factor,
        prediction.reshape(-1, prediction.shape[-1]),
        sigma_hz=config.signal_sigma_hz,
        effective_count=effective_count,
        visible=visible.ravel(),
    )
    train = np.asarray(flat["training_log_likelihood"]).reshape(prediction.shape[:2])
    heldout = np.asarray(flat["heldout_log_likelihood"]).reshape(prediction.shape[:2])
    null = score_paired_doppler_factor(
        factor,
        np.zeros((1, prediction.shape[-1])),
        sigma_hz=config.null_sigma_hz,
        effective_count=effective_count,
    )
    null_train = float(np.asarray(null["training_log_likelihood"])[0])
    null_heldout = float(np.asarray(null["heldout_log_likelihood"])[0])
    return [
        component_log_evidence(
            train[index],
            heldout[index],
            null_train,
            null_heldout,
            population,
            config.signal_prior,
        )
        for index in range(len(prediction))
    ]


def _verify_refinement(path: Path) -> dict:
    result = json.loads(path.read_text())
    checksum = path.with_name("result.sha256")
    seal = path.with_name("refinement-seal.json")
    seal_doc = json.loads(seal.read_text())
    if (
        checksum.read_text().strip() != hashlib.sha256(path.read_bytes()).hexdigest()
        or seal_doc.get("result_digest") != digest(path)
        or not seal_doc.get("all_fits_converged")
        or result.get("position_truth_used") is not False
        or result.get("complete") is not True
    ):
        raise ValueError("sealed converged truth-free refinement required")
    return result


def run(args) -> None:
    if args.output.exists():
        raise FileExistsError(args.output)
    authority = json.loads(args.authority.read_text())
    authority_content = content_digest(authority)
    if authority.get("truth_accessed") or authority.get("site_conditioned_candidates_used"):
        raise ValueError("blind RF-only authority required")
    evidence = json.loads(args.evidence.read_text())
    inventory = evidence["inventory"]
    if authority["shard_sha256"] != inventory["source_shard_digest"]:
        raise ValueError("authority and evidence bind different RF shards")
    tle_path = args.evidence.parent / inventory["tle_file"]
    if Path(inventory["tle_file"]).name != inventory["tle_file"]:
        raise ValueError("unsafe TLE basename")
    if digest(tle_path) != inventory["tle_digest"]:
        raise ValueError("TLE digest mismatch")
    if inventory["tle_collected_ns"] >= inventory["reference_utc_ns"] - 5_000_000_000:
        raise ValueError("noncausal TLE snapshot")
    replay, replay_path = _load_replay()
    catalogue = parse_element_sets(tle_path.read_text())
    series = {row["tracklet_id"]: row for row in evidence["series"]}
    if len(series) != len(evidence["series"]):
        raise ValueError("duplicate evidence series")
    visit_by_group = _visit_map(authority)
    branch_rows = []
    for refinement_path in args.refinement:
        refinement = _verify_refinement(refinement_path)
        acquisition = json.loads((Path(refinement["run"]) / "result.json").read_text())
        config = ScoreConfig(**acquisition["score"])
        region = Region(**refinement["region"])
        selected = refinement["selected"]
        offsets = np.asarray([-args.stencil_km, 0.0, args.stencil_km])
        east = selected["east_km"] + np.tile(offsets, 3)
        north = selected["north_km"] + np.repeat(offsets, 3)
        grid = region.points(east, north)
        indices, population = replay.regional_catalogue(
            catalogue, inventory["reference_utc_ns"], region
        )
        totals = {q: np.zeros((len(east), 2), dtype=float) for q in Q_ARMS}
        accounting, exclusions = [], []
        for link in authority["authorized_track_pairs"]:
            left_id, right_id = link["rx0_tracklet_id"], link["rx1_tracklet_id"]
            left, right = series[left_id], series[right_id]
            excluded_left = {row["rx0_source_group_id"] for row in link["anchors"]}
            excluded_right = {row["rx1_source_group_id"] for row in link["anchors"]}
            try:
                partition = shared_five_block_partition(
                    left, right, excluded_left, excluded_right, visit_by_group
                )
                left_arc, left_visit = _arc(left, excluded_left, partition, visit_by_group)
                right_arc, right_visit = _arc(right, excluded_right, partition, visit_by_group)
                states = []
                evidences = []
                for arc, visits in ((left_arc, left_visit), (right_arc, right_visit)):
                    p, v, retained = replay.state_arrays(
                        catalogue, indices, inventory["reference_utc_ns"], arc.time_s
                    )
                    norad = np.asarray(catalogue.satellite_numbers)[retained]
                    factor = PairedDopplerFactor(
                        observed_hz=arc.frequency_hz,
                        receiver_id=arc.segment,
                        visit_id=visits,
                        training=arc.training,
                        pairing_authority=authority_content,
                    )
                    prediction, elevation = _prediction(p, v, grid)
                    visible = np.min(elevation[..., arc.training], axis=-1) >= np.sin(
                        np.deg2rad(config.minimum_elevation_deg)
                    )
                    evidences.append(
                        _factor_evidence(factor, prediction, visible, population, config, 3.0)
                    )
                    states.append((arc, p, v, norad, visits))
                if not np.array_equal(states[0][3], states[1][3]):
                    raise ValueError("paired paths retain different candidate support")
                combined_arc = ObservationArc(
                    np.r_[left_arc.time_s, right_arc.time_s],
                    np.r_[left_arc.frequency_hz, right_arc.frequency_hz],
                    np.r_[left_arc.segment, right_arc.segment],
                    np.r_[left_arc.training, right_arc.training],
                    partition="randomized",
                )
                combined_visits = np.r_[left_visit, right_visit]
                combined_factor = PairedDopplerFactor(
                    observed_hz=combined_arc.frequency_hz,
                    receiver_id=combined_arc.segment,
                    visit_id=combined_visits,
                    training=combined_arc.training,
                    pairing_authority=authority_content,
                )
                combined_p = np.concatenate((states[0][1], states[1][1]), axis=1)
                combined_v = np.concatenate((states[0][2], states[1][2]), axis=1)
                prediction, elevation = _prediction(combined_p, combined_v, grid)
                visible = np.min(elevation[..., combined_arc.training], axis=-1) >= np.sin(
                    np.deg2rad(config.minimum_elevation_deg)
                )
                shared = _factor_evidence(
                    combined_factor, prediction, visible, population, config, 6.0
                )
                for point in range(len(east)):
                    independent_train = evidences[0][point][0] + evidences[1][point][0]
                    independent_joint = evidences[0][point][1] + evidences[1][point][1]
                    for q in Q_ARMS:
                        mixed_train = mixed_log_evidence(independent_train, shared[point][0], q)
                        mixed_joint = mixed_log_evidence(independent_joint, shared[point][1], q)
                        totals[q][point, 0] += mixed_train - independent_train
                        totals[q][point, 1] += (mixed_joint - mixed_train) - (
                            independent_joint - independent_train
                        )
                accounting.append(
                    {
                        "rx0_tracklet_id": left_id,
                        "rx1_tracklet_id": right_id,
                        "excluded_authority_rows": len(excluded_left) + len(excluded_right),
                        "rx0_retained_rows": len(left_arc.time_s),
                        "rx1_retained_rows": len(right_arc.time_s),
                        "candidate_count": len(states[0][3]),
                        "full_catalogue_size": population,
                    }
                )
            except ValueError as error:
                exclusions.append(
                    {"rx0_tracklet_id": left_id, "rx1_tracklet_id": right_id, "reason": str(error)}
                )
        arms = [{"q": 0.0, "points": []}]
        for q in Q_ARMS:
            points = []
            for index in range(len(east)):
                points.append(
                    {
                        "east_km": float(east[index]),
                        "north_km": float(north[index]),
                        "soft_minus_independent_training_log_score": float(totals[q][index, 0]),
                        "soft_minus_independent_heldout_log_score": float(totals[q][index, 1]),
                    }
                )
            arms.append({"q": q, "points": points})
        arms[0]["points"] = [
            {
                "east_km": float(east[index]),
                "north_km": float(north[index]),
                "soft_minus_independent_training_log_score": 0.0,
                "soft_minus_independent_heldout_log_score": 0.0,
            }
            for index in range(len(east))
        ]
        branch_rows.append(
            {
                "branch": refinement_path.parent.name,
                "center": {"east_km": selected["east_km"], "north_km": selected["north_km"]},
                "arms": arms,
                "qualified_pair_count": len(accounting),
                "excluded_pair_count": len(exclusions),
                "pair_accounting": accounting,
                "exclusions": exclusions,
                "refinement_digest": digest(refinement_path),
            }
        )
    output = {
        "schema": "soft-receiver-pair-five-block-stencil/v1",
        "truth_accessed": False,
        "position_selection_performed": False,
        "matched_independent_control_delta": 0.0,
        "interpretation": "pair-factor score delta conditional on sealed five-block finalists",
        "direct_baseline_score_comparison_valid": False,
        "direct_baseline_reason": (
            "authority rows are removed and linked paths use one shared-visit five-block split"
        ),
        "q_arms": list(Q_ARMS),
        "branches": branch_rows,
        "limitations": [
            "composite scores are not calibrated likelihoods",
            "pair authority is retrospective and unresolved modulo pilot alias",
            "only scan-1d supplies authorized pairs; four other scans only selected "
            "the frozen basin",
            "80 mm mechanical spacing supplies no phase, angle, or useful kilometre-scale baseline",
        ],
        "provenance": {
            "authority_digest": digest(args.authority),
            "authority_content_digest": authority_content,
            "evidence_digest": digest(args.evidence),
            "tle_digest": digest(tle_path),
            "replay_digest": digest(replay_path),
            "source_digest": digest(Path(__file__)),
        },
    }
    output["content_digest"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refinement", type=Path, action="append", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stencil-km", type=float, default=10.0)
    run(parser.parse_args())
