#!/usr/bin/env python3
"""Frozen TRAIN-only paired-receiver residual diagnostic."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
POOLED = ROOT / "reports/2026_09_23_pooled_train_position/results/inference.json"
INVENTORY = ROOT / "reports/2026_09_23_long_inventory_complete/manifest.json"
FIRST = ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/results/inference.json"
SECOND = ROOT / "reports/2026_09_23_second_train_epoch_replication/results/inference.json"
HELPER = ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/fit.py"
SINGLE = ROOT / "reports/2026_09_23_long_training_search/search.py"
METADATA = Path("/tmp/leo-train-rx-metadata.json")
CACHES = (
    Path("/tmp/leo-long-training-cache-full8h"),
    Path("/tmp/leo-long-training-cache-second8h"),
)
SEED = 20260923


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def nearest_pairs(left_ns, right_ns, tolerance_ms=80):
    """Return deterministic one-to-one nearest pairs within the tolerance."""
    possible = sorted(
        (abs(int(a) - int(b)), i, j)
        for i, a in enumerate(left_ns)
        for j, b in enumerate(right_ns)
        if abs(int(a) - int(b)) <= tolerance_ms * 1_000_000
    )
    used_left, used_right, result = set(), set(), []
    for delta, i, j in possible:
        if i not in used_left and j not in used_right:
            used_left.add(i)
            used_right.add(j)
            result.append((i, j, delta))
    return sorted(result)


def polynomial_terms(times_s, values_hz):
    centre = np.asarray(times_s, dtype=float) - np.mean(times_s)
    design = np.column_stack((np.ones(len(centre)), centre, centre**2))
    return np.linalg.lstsq(design, np.asarray(values_hz), rcond=None)[0][1:]


def summarize(rows, key, groups, bootstrap_count=5000):
    values = np.asarray([row[key] for row in rows], dtype=float)
    estimate = float(np.mean(values))
    by_group = {
        group: [i for i, row in enumerate(rows) if row["group"] == group] for group in groups
    }
    rng = np.random.default_rng(SEED)
    draws = []
    for _ in range(bootstrap_count):
        sampled = rng.choice(groups, len(groups), replace=True)
        indices = [i for group in sampled for i in by_group[group]]
        draws.append(float(np.mean(values[indices])))
    return {
        "mean": estimate,
        "median": float(np.median(values)),
        "ci95": [float(x) for x in np.quantile(draws, [0.025, 0.975])],
        "pair_count": len(rows),
        "group_count": len(groups),
    }


def select_arm(pooled):
    matches = [a for a in pooled["arms"] if a["prior"] == "sacramento" and a["scale_s"] == 5.0]
    if len(matches) != 1:
        raise ValueError("sealed Sacramento scale-5 arm is not unique")
    return matches[0]


def validate_and_prepare():
    pooled, metadata = json.loads(POOLED.read_text()), json.loads(METADATA.read_text())
    inventory = json.loads(INVENTORY.read_text())["partitions"]
    session_ids = pooled["groups"][0] + pooled["groups"][1]
    if len(session_ids) != 151 or len(set(session_ids)) != 151:
        raise ValueError("pooled cohort is not exactly 151 unique sessions")
    if session_ids != inventory["train"]["session_ids"]:
        raise ValueError("pooled cohort differs from frozen TRAIN inventory")
    if set(session_ids) & set(
        inventory["validation"]["session_ids"] + inventory["test"]["session_ids"]
    ):
        raise ValueError("TRAIN cohort overlaps VAL/TEST")
    if [row["session_id"] for row in metadata["sessions"]] != session_ids:
        raise ValueError("metadata order/membership differs from frozen TRAIN")

    helper, single = load_module(HELPER, "rx_helper"), load_module(SINGLE, "rx_single")
    arm = select_arm(pooled)
    parents = [json.loads(FIRST.read_text()), json.loads(SECOND.read_text())]
    parent_arms = [
        next(
            row
            for row in parents[0]["arms"]
            if row["prior"] == "sacramento" and row["scale_s"] == 5.0
        ),
        next(
            row
            for row in parents[1]["arms"]
            if row["prior"] == "sacramento"
            and row["scale_s"] == 5.0
            and row["model"] == "scan"
            and row["view_scan_count"] == 79
        ),
    ]
    fixed = defaultdict(list)
    for group, parent_arm in zip(pooled["groups"], parent_arms, strict=True):
        for sid in group:
            fixed[sid] = [r for r in parent_arm["fixed_tracks"] if r["session_id"] == sid]
            if not fixed[sid]:
                raise ValueError(f"no fixed tracks for {sid}")
    tracks = []
    bindings = []
    metadata_by_session = {row["session_id"]: row for row in metadata["sessions"]}
    anchors = {}
    for group, cache in zip(pooled["groups"], CACHES, strict=True):
        scans = [{"session_id": sid, "tracks": fixed[sid]} for sid in group]
        current, current_bindings = helper.prepare(single, cache, group, scans)
        expected = {
            (sid, row["track_id"], row["candidate_id"]) for sid in group for row in fixed[sid]
        }
        observed = {(row["session_id"], row["track_id"], row["candidate_id"]) for row in current}
        if observed != expected:
            raise ValueError("prepared fixed (session, track, candidate) support differs")
        tracks.extend(current)
        bindings.extend(current_bindings)
        for sid, binding in zip(group, current_bindings, strict=True):
            recovered = metadata_by_session[sid]
            if (
                binding["receipt"] != recovered["cache_receipt"]
                or binding["cache"] != recovered["state_cache"]
            ):
                raise ValueError(f"cache binding mismatch: {sid}")
            receipt = json.loads((cache / sid / "cache_receipt.json").read_text())
            receipt_tracks = {r["track_id"]: r for r in receipt["prepared_evidence"]["tracks"]}
            recovered_tracks = {r["track_id"]: r for r in recovered["tracks"]}
            if set(recovered_tracks) != set(receipt_tracks):
                raise ValueError(f"recovered/prepared track set mismatch: {sid}")
            anchor_values = []
            for track_id, row in recovered_tracks.items():
                source = receipt_tracks[track_id]
                if row["observation_ids"] != source["observation_ids"]:
                    raise ValueError(f"observation join mismatch: {sid}/{track_id}")
                if len(row["support_center_utc_ns"]) != len(source["times_s"]):
                    raise ValueError(f"sample join mismatch: {sid}/{track_id}")
                anchor_values.extend(
                    int(utc) - int(round(relative * 1e9))
                    for utc, relative in zip(
                        row["support_center_utc_ns"], source["times_s"], strict=True
                    )
                )
            # Do not median nanosecond epochs through float64 (it loses ~100 ns here).
            anchor = anchor_values[0]
            if max(abs(value - anchor) for value in anchor_values) > 2:
                raise ValueError(f"non-constant UTC/relative anchor: {sid}")
            anchors[sid] = anchor
            if (
                not recovered["tle_snapshot_digest"]
                or recovered["tle_snapshot_collected_utc_ns"] >= anchor
            ):
                raise ValueError(f"missing or non-causal TLE binding: {sid}")
    return pooled, metadata_by_session, tracks, arm, single, helper, bindings, anchors


def build_rows(metadata, tracks, arm, single, helper, tolerance_ms=80):
    point = arm["latitude_deg"], arm["longitude_deg"]
    receiver, _ = single.receiver_ecef(*point)
    latitude, longitude = np.radians(point)
    east = np.array([-np.sin(longitude), np.cos(longitude), 0.0])
    north = np.array(
        [
            -np.sin(latitude) * np.cos(longitude),
            -np.sin(latitude) * np.sin(longitude),
            np.cos(latitude),
        ]
    )
    track_map = {(t["session_id"], t["track_id"]): t for t in tracks}
    candidates = defaultdict(lambda: defaultdict(list))
    enriched = {}
    for key, track in track_map.items():
        sid, track_id = key
        row = next(r for r in metadata[sid]["tracks"] if r["track_id"] == track_id)
        mask = track["training_mask"]
        position, velocity = helper.interpolate(track, arm["taus_s"][sid])
        delta = position - receiver
        distance = np.linalg.norm(delta, axis=1)
        prediction = (
            -single.REFERENCE_RF_HZ
            / single.LIGHT_KM_S
            * np.sum(delta * velocity, axis=1)
            / distance
        )
        residual = track["measured_hz"] - prediction
        residual -= np.mean(residual[mask])
        item = {
            **row,
            "candidate_id": track["candidate_id"],
            "times_s": track["times_s"],
            "training_mask": mask,
            "residual_hz": residual,
            "position": position,
        }
        enriched[key] = item
        receiver_id = (
            f"rx{row['receiver_id']}" if isinstance(row["receiver_id"], int) else row["receiver_id"]
        )
        item["receiver_id"] = receiver_id
        candidates[(sid, track["candidate_id"])][receiver_id].append(item)

    rejection, output = Counter(), []
    receivers = sorted(
        {
            r["receiver_id"]
            for groups in candidates.values()
            for rows in groups.values()
            for r in rows
        }
    )
    if receivers != ["rx0", "rx1"]:
        raise ValueError(f"expected rx0/rx1, got {receivers}")
    for (sid, candidate_id), by_receiver in candidates.items():
        if not by_receiver["rx0"] or not by_receiver["rx1"]:
            rejection["missing_opposite_receiver"] += sum(map(len, by_receiver.values()))
            continue
        for left in by_receiver["rx0"]:
            for right in by_receiver["rx1"]:
                if (left["channel"], left["edge"], left["sample_rate_hz"]) != (
                    right["channel"],
                    right["edge"],
                    right["sample_rate_hz"],
                ):
                    rejection["lane_or_sample_rate_mismatch"] += 1
                    continue
                overlap_ns = min(left["support_end_utc_ns"], right["support_end_utc_ns"]) - max(
                    left["support_start_utc_ns"], right["support_start_utc_ns"]
                )
                if overlap_ns < 3_000_000_000:
                    rejection["overlap_under_3s"] += 1
                    continue
                li = np.flatnonzero(left["training_mask"])
                ri = np.flatnonzero(right["training_mask"])
                matches = nearest_pairs(
                    np.asarray(left["support_center_utc_ns"])[li],
                    np.asarray(right["support_center_utc_ns"])[ri],
                    tolerance_ms,
                )
                if len(matches) < 8:
                    rejection["fewer_than_8_time_matches"] += 1
                    continue
                lidx = np.asarray([li[i] for i, _, _ in matches])
                ridx = np.asarray([ri[j] for _, j, _ in matches])
                lf = np.asarray(left["measured_cfo_hz"])[lidx]
                rf = np.asarray(right["measured_cfo_hz"])[ridx]
                frequency_disagreement = float(
                    np.median(np.abs((lf - np.median(lf)) - (rf - np.median(rf))))
                )
                if frequency_disagreement >= 2000:
                    rejection["centered_frequency_disagreement_ge_2khz"] += 1
                    continue
                times = (left["times_s"][lidx] + right["times_s"][ridx]) / 2
                lr, rr = left["residual_hz"][lidx], right["residual_hz"][ridx]
                differential = lr - rr
                common = (lr + rr) / 2
                ds, dc = polynomial_terms(times, differential)
                cs, cc = polynomial_terms(times, common)
                midpoint = (
                    left["position"][lidx[len(lidx) // 2]] + right["position"][ridx[len(ridx) // 2]]
                ) / 2 - receiver
                group = f"{sid}/{candidate_id}"
                output.append(
                    {
                        "session_id": sid,
                        "candidate_id": candidate_id,
                        "group": group,
                        "rx0_track_id": left["track_id"],
                        "rx1_track_id": right["track_id"],
                        "lane": (
                            f"{left['channel']}/{left['edge']}/"
                            f"{left['actual_rf_hz']}/{left['sample_rate_hz']}"
                        ),
                        "match_count": len(matches),
                        "overlap_s": overlap_ns / 1e9,
                        "maximum_time_mismatch_ms": max(x[2] for x in matches) / 1e6,
                        "median_centered_frequency_disagreement_hz": frequency_disagreement,
                        "differential_slope_hz_s": float(ds),
                        "differential_quadratic_hz_s2": float(dc),
                        "common_slope_hz_s": float(cs),
                        "common_quadratic_hz_s2": float(cc),
                        "snapshot_collection_age_s": (
                            np.mean(
                                (
                                    np.asarray(left["support_center_utc_ns"])[lidx]
                                    + np.asarray(right["support_center_utc_ns"])[ridx]
                                )
                                / 2
                            )
                            - metadata[sid]["tle_snapshot_collected_utc_ns"]
                        )
                        / 1e9,
                        "look_quadrant": ("E" if midpoint @ east >= 0 else "W")
                        + ("N" if midpoint @ north >= 0 else "S"),
                    }
                )
    return output, rejection, len(candidates)


def analyze():
    pooled, metadata, tracks, arm, single, helper, bindings, anchors = validate_and_prepare()
    pairs, rejection, provisional_groups = build_rows(metadata, tracks, arm, single, helper)
    groups = sorted({row["group"] for row in pairs})
    if not pairs:
        raise ValueError("no receiver pairs passed frozen gates")
    first_group = set(pooled["groups"][0])
    for row in pairs:
        row["train_group"] = "first8h" if row["session_id"] in first_group else "second8h"
    effects = {
        key: summarize(pairs, key, groups)
        for key in (
            "differential_slope_hz_s",
            "differential_quadratic_hz_s2",
            "common_slope_hz_s",
            "common_quadratic_hz_s2",
        )
    }
    strata = {}
    for field in ("look_quadrant",):
        strata[field] = {}
        for value in sorted({row[field] for row in pairs}, key=str):
            subset = [row for row in pairs if row[field] == value]
            subset_groups = sorted({row["group"] for row in subset})
            strata[field][str(value)] = {
                key: summarize(subset, key, subset_groups, 2000)
                for key in ("common_slope_hz_s", "common_quadratic_hz_s2")
            }
    consistency = {}
    for field in ("train_group", "lane"):
        consistency[field] = {}
        for value in sorted({row[field] for row in pairs}):
            subset = [row for row in pairs if row[field] == value]
            subset_groups = sorted({row["group"] for row in subset})
            consistency[field][value] = {
                key: summarize(subset, key, subset_groups, 2000)
                for key in ("differential_slope_hz_s", "common_slope_hz_s")
            }
    track_use = Counter(
        track_id for row in pairs for track_id in (row["rx0_track_id"], row["rx1_track_id"])
    )
    sensitivity = {}
    for tolerance in (40, 80, 120):
        rows, rejects, _ = build_rows(metadata, tracks, arm, single, helper, tolerance)
        sensitivity[str(tolerance)] = {
            "pair_count": len(rows),
            "matched_sample_count": sum(r["match_count"] for r in rows),
            "rejections": dict(sorted(rejects.items())),
        }
    return {
        "schema": "leo.train_receiver_orbit_diagnostic.v1",
        "seed": SEED,
        "support": {
            "train_session_count": len(pooled["groups"][0] + pooled["groups"][1]),
            "fixed_track_count": len(tracks),
            "provisional_scan_candidate_count": provisional_groups,
            "passing_pair_count": len(pairs),
            "passing_group_count": len(groups),
            "matched_sample_count": sum(r["match_count"] for r in pairs),
            "receiver_ids": ["rx0", "rx1"],
            "rejections": dict(sorted(rejection.items())),
            "tracks_reused_across_passing_pairs": sum(value > 1 for value in track_use.values()),
            "maximum_passing_pairs_per_track": max(track_use.values()),
        },
        "effects": effects,
        "common_strata": strata,
        "consistency_strata": consistency,
        "element_age_strata": {
            "status": "unavailable",
            "reason": "sealed state cache omits per-candidate element epochs",
        },
        "time_mismatch_sensitivity": sensitivity,
        "pairs": pairs,
        "bindings": {
            "pooled_inference": digest(POOLED),
            "inventory": digest(INVENTORY),
            "metadata": digest(METADATA),
            "helper": digest(HELPER),
            "single": digest(SINGLE),
            "fixed_track_parents": [digest(FIRST), digest(SECOND)],
            "cache_bindings": bindings,
            "tle_digests": {sid: metadata[sid]["tle_snapshot_digest"] for sid in metadata},
            "capture_analysis_manifests": {
                sid: {
                    "input_manifest": metadata[sid]["input_manifest"],
                    "analysis_manifest": metadata[sid]["analysis_manifest"],
                }
                for sid in metadata
            },
            "analyzer": digest(Path(__file__)),
        },
        "recovery_accounting": {
            "expected_sessions": 151,
            "successful_sessions": len(metadata),
            "failed_sessions": 0,
        },
        "utc_anchor_range_ns": [min(anchors.values()), max(anchors.values())],
        "held_rows_used": False,
        "validation_or_test_used": False,
        "reference_coordinate_used": False,
        "position_refit_performed": False,
    }


def plot(result, output):
    rows = result["pairs"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].scatter(
        [r["snapshot_collection_age_s"] / 3600 for r in rows],
        [r["common_slope_hz_s"] for r in rows],
        s=12,
        alpha=0.55,
    )
    axes[0].set(xlabel="Snapshot collection age (h)", ylabel="Common residual slope (Hz/s)")
    axes[1].scatter(
        [r["differential_slope_hz_s"] for r in rows],
        [r["differential_quadratic_hz_s2"] for r in rows],
        s=12,
        alpha=0.55,
    )
    axes[1].set(xlabel="RX0−RX1 slope (Hz/s)", ylabel="RX0−RX1 quadratic coefficient (Hz/s²)")
    fig.suptitle("Frozen TRAIN paired-receiver residual diagnostic")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main():
    output = HERE / "results"
    if output.exists():
        raise FileExistsError("fresh output required")
    result = analyze()
    output.mkdir()
    path = output / "inference.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(digest(path).split(":", 1)[1] + "\n")
    plot(result, output / "diagnostic.png")


if __name__ == "__main__":
    main()
