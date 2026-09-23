#!/usr/bin/env python3
"""Matched full-grid independent versus RF-authorized paired identity comparison."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

from leo.analysis.research.paired_receiver_geometry import (
    PairedDopplerFactor,
    score_paired_states,
)
from leo.analysis.research.regional_doppler import Grid, ObservationArc
from leo.sky.propagation import parse_element_sets


def _replay():
    path = Path(__file__).parents[1] / "replay_regional_doppler.py"
    spec = importlib.util.spec_from_file_location("paired_grid_replay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("regional replay helper unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def _digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_content_digest(document):
    claimed = document.get("content_digest")
    payload = dict(document)
    payload.pop("content_digest", None)
    actual = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    if claimed != actual:
        raise ValueError("authority content digest differs")


def _arc(series, excluded, training_by_visit, visit_by_group):
    keep = np.asarray([value not in excluded for value in series["paired_visit_ids"]])
    if np.sum(keep) < 4:
        raise ValueError("anchor exclusion leaves fewer than four observations")
    count = int(np.sum(keep))
    groups = np.asarray(series["paired_visit_ids"])[keep]
    training = np.asarray([training_by_visit[visit_by_group[value]] for value in groups])
    return ObservationArc(
        time_s=np.asarray(series["t_s"])[keep],
        frequency_hz=np.asarray(series["y_hz"])[keep],
        segment=np.asarray([series["tracklet_id"]] * count),
        training=training,
    )


def _shared_partition(left, right, excluded_left, excluded_right, visit_by_group):
    left_visits = [
        visit_by_group[group] for group in left["paired_visit_ids"] if group not in excluded_left
    ]
    right_visits = [
        visit_by_group[group] for group in right["paired_visit_ids"] if group not in excluded_right
    ]
    visits = sorted(set((*left_visits, *right_visits)))
    candidates = []
    for cut in range(2, len(visits) - 1):
        training = set(visits[:cut])
        counts = (
            sum(value in training for value in left_visits),
            sum(value not in training for value in left_visits),
            sum(value in training for value in right_visits),
            sum(value not in training for value in right_visits),
        )
        if min(counts) >= 2:
            candidates.append((abs(cut / len(visits) - 0.6), cut, training))
    if not candidates:
        raise ValueError("paired paths cannot support one shared train/heldout partition")
    training = min(candidates, key=lambda item: (item[0], item[1]))[2]
    return {visit: visit in training for visit in visits}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    replay, replay_path = _replay()
    evidence = json.loads(args.evidence.read_text())
    authority = json.loads(args.authority.read_text())
    _verify_content_digest(authority)
    if authority["truth_accessed"] or authority["site_conditioned_candidates_used"]:
        raise ValueError("pair authority is not blind")
    inventory = evidence["inventory"]
    if authority["shard_sha256"] != inventory["source_shard_digest"]:
        raise ValueError("pair authority and regional evidence bind different RF shards")
    if Path(inventory["tle_file"]).name != inventory["tle_file"]:
        raise ValueError("TLE input must be an evidence-local basename")
    tle_path = args.evidence.parent / inventory["tle_file"]
    if _digest(tle_path) != inventory["tle_digest"]:
        raise ValueError("TLE input digest differs")
    if inventory["tle_collected_ns"] >= inventory["reference_utc_ns"] - 5_000_000_000:
        raise ValueError("TLE input is not causal")
    catalogue = parse_element_sets(tle_path.read_text())
    from leo.analysis.research.regional_doppler import Region

    branch_result = json.loads((args.branch / "result.json").read_text())
    if branch_result.get("position_truth_used") is not False:
        raise ValueError("branch acquisition is not blind")
    seal_path = args.branch / "acquisition-seal.json"
    if not seal_path.is_file():
        raise ValueError("sealed branch acquisition is required")
    seal = json.loads(seal_path.read_text())
    session_archive = f"{inventory['session_id']}.npz"
    for name in ("grid.npz", "result.json", "configuration.json", "history.json", session_archive):
        if seal.get("files", {}).get(name) != _digest(args.branch / name):
            raise ValueError(f"sealed acquisition file differs: {name}")
    configuration = json.loads((args.branch / "configuration.json").read_text())
    if configuration.get("clock_s") != 0.0 or configuration.get("altitude_m") != 0.0:
        raise ValueError("paired replay supports only the executed zero clock/altitude acquisition")
    history = json.loads((args.branch / "history.json").read_text())
    history_row = next(
        (item for item in history if item["session_id"] == inventory["session_id"]), None
    )
    if history_row is None or history_row["source_digest"] != _digest(args.evidence):
        raise ValueError("regional evidence does not bind acquisition history")
    region = Region(**branch_result["region"])
    indices, population = replay.regional_catalogue(
        catalogue, inventory["reference_utc_ns"], region
    )
    with np.load(args.branch / "grid.npz") as saved:
        grid = Grid(**{key: saved[key] for key in Grid.__dataclass_fields__})
    with np.load(args.branch / f"{inventory['session_id']}.npz") as saved:
        original_train = saved["train_logbf"]
        original_heldout = saved["heldout_logbf"]
    episode_order = [item["episode_id"] for item in evidence["episodes"]]
    series = {item["tracklet_id"]: item for item in evidence["series"]}
    track_to_episode = {
        member: item["episode_id"] for item in evidence["episodes"] for member in item["members"]
    }
    links = authority["authorized_track_pairs"]
    visit_by_group = {}
    for item in authority["rf_detection_table"]:
        prior = visit_by_group.setdefault(item["source_group_id"], item["visit"])
        if prior != item["visit"]:
            raise ValueError("one source group maps to multiple visits")
    qualified_links = []
    excluded_links = []
    for link in links:
        left_id, right_id = link["rx0_tracklet_id"], link["rx1_tracklet_id"]
        excluded_left = {item["rx0_source_group_id"] for item in link["anchors"]}
        excluded_right = {item["rx1_source_group_id"] for item in link["anchors"]}
        try:
            partition = _shared_partition(
                series[left_id],
                series[right_id],
                excluded_left,
                excluded_right,
                visit_by_group,
            )
        except ValueError:
            excluded_links.append(
                {
                    "rx0_tracklet_id": left_id,
                    "rx1_tracklet_id": right_id,
                    "reason": "insufficient_rows_for_shared_visit_partition_after_anchor_exclusion",
                }
            )
            continue
        qualified_links.append((link, partition))
    ownership = [
        value
        for link, _partition in qualified_links
        for value in (link["rx0_tracklet_id"], link["rx1_tracklet_id"])
    ]
    if len(set(ownership)) != len(ownership):
        raise ValueError("pair authority has ambiguous many-to-one track ownership")
    linked_rows = {episode_order.index(track_to_episode[value]) for value in ownership}
    unlinked_train = np.sum(np.delete(original_train, sorted(linked_rows), axis=0), axis=0)
    unlinked_heldout = np.sum(np.delete(original_heldout, sorted(linked_rows), axis=0), axis=0)
    independent_train = unlinked_train.copy()
    independent_heldout = unlinked_heldout.copy()
    paired_train = unlinked_train.copy()
    paired_heldout = unlinked_heldout.copy()
    score_settings = configuration["score"]

    def score_factor(factor, p, v, effective_count):
        return score_paired_states(
            factor,
            p,
            v,
            grid,
            population,
            signal_sigma_hz=score_settings["signal_sigma_hz"],
            null_sigma_hz=score_settings["null_sigma_hz"],
            signal_prior=score_settings["signal_prior"],
            effective_count=effective_count,
            minimum_elevation_deg=score_settings["minimum_elevation_deg"],
        )

    accounting = []
    for link, partition in qualified_links:
        left_id, right_id = link["rx0_tracklet_id"], link["rx1_tracklet_id"]
        excluded_left = {item["rx0_source_group_id"] for item in link["anchors"]}
        excluded_right = {item["rx1_source_group_id"] for item in link["anchors"]}
        left_arc, right_arc = (
            _arc(series[left_id], excluded_left, partition, visit_by_group),
            _arc(series[right_id], excluded_right, partition, visit_by_group),
        )
        states = []
        path_inputs = (
            (left_arc, series[left_id], excluded_left),
            (right_arc, series[right_id], excluded_right),
        )
        for arc, path_series, excluded in path_inputs:
            p, v, retained = replay.state_arrays(
                catalogue, indices, inventory["reference_utc_ns"], arc.time_s
            )
            states.append((arc, p, v, np.asarray(catalogue.satellite_numbers)[retained]))
            factor = PairedDopplerFactor(
                observed_hz=arc.frequency_hz,
                receiver_id=arc.segment,
                visit_id=np.asarray(
                    [
                        visit_by_group[value]
                        for value in path_series["paired_visit_ids"]
                        if value not in excluded
                    ]
                ),
                training=arc.training,
                pairing_authority=authority["content_digest"],
            )
            score = score_factor(factor, p, v, 3.0)
            independent_train += score["train_logbf"]
            independent_heldout += score["heldout_logbf"]
        common = np.intersect1d(states[0][3], states[1][3])
        if not np.array_equal(states[0][3], states[1][3]):
            raise ValueError("paired paths do not retain identical full candidate support")
        combined = ObservationArc(
            time_s=np.r_[left_arc.time_s, right_arc.time_s],
            frequency_hz=np.r_[left_arc.frequency_hz, right_arc.frequency_hz],
            segment=np.r_[left_arc.segment, right_arc.segment],
            training=np.r_[left_arc.training, right_arc.training],
        )
        p = np.concatenate((states[0][1], states[1][1]), axis=1)
        v = np.concatenate((states[0][2], states[1][2]), axis=1)
        combined_factor = PairedDopplerFactor(
            observed_hz=combined.frequency_hz,
            receiver_id=combined.segment,
            visit_id=np.asarray(
                [
                    visit_by_group[value]
                    for value in series[left_id]["paired_visit_ids"]
                    if value not in excluded_left
                ]
                + [
                    visit_by_group[value]
                    for value in series[right_id]["paired_visit_ids"]
                    if value not in excluded_right
                ]
            ),
            training=combined.training,
            pairing_authority=authority["content_digest"],
        )
        score = score_factor(combined_factor, p, v, 6.0)
        paired_train += score["train_logbf"]
        paired_heldout += score["heldout_logbf"]
        accounting.append(
            {
                "rx0_tracklet_id": left_id,
                "rx1_tracklet_id": right_id,
                "excluded_anchor_rows": len(excluded_left) + len(excluded_right),
                "retained_observations": len(combined.time_s),
                "candidate_count": len(common),
            }
        )

    def selected(train, heldout):
        index = int(np.argmax(train))
        return {
            "grid_index": index,
            "east_km": float(grid.east_km[index]),
            "north_km": float(grid.north_km[index]),
            "latitude_deg": float(grid.latitude_deg[index]),
            "longitude_deg": float(grid.longitude_deg[index]),
            "training_score": float(train[index]),
            "heldout_score": float(heldout[index]),
        }

    document = {
        "schema": "recent-paired-blind-grid-comparison/v1",
        "truth_accessed": False,
        "known_position_used": False,
        "site_conditioned_candidates_used": False,
        "branch": args.branch.name,
        "region": branch_result["region"],
        "score": {
            "full_catalogue_prior_denominator": population,
            "explicit_null": True,
            "paired_effective_count": 6.0,
            "independent_effective_count_per_path": 3.0,
            "pair_total_effective_count": 6.0,
            "paired_offsets": "separate constant per receiver path",
        },
        "independent": selected(independent_train, independent_heldout),
        "paired": selected(paired_train, paired_heldout),
        "pair_accounting": accounting,
        "excluded_pair_accounting": excluded_links,
        "limitations": [
            "pair authority was extracted retrospectively from held-out odd visits",
            "all authority anchor rows are excluded from both position arms",
            "composite scores are not calibrated likelihoods",
            "paired geometry is shared temporal Doppler shape, not baseline triangulation",
        ],
        "provenance": {
            "evidence": _digest(args.evidence),
            "authority": _digest(args.authority),
            "grid": _digest(args.branch / "grid.npz"),
            "branch_result": _digest(args.branch / "result.json"),
            "acquisition_seal": _digest(seal_path),
            "coarse_scores": _digest(args.branch / f"{inventory['session_id']}.npz"),
            "tle": _digest(tle_path),
            "runner": _digest(Path(__file__)),
            "replay_helper": _digest(replay_path),
        },
    }
    document["content_digest"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"independent": document["independent"], "paired": document["paired"]}))


if __name__ == "__main__":
    main()
