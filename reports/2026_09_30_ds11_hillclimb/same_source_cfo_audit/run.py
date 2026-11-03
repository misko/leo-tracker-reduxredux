#!/usr/bin/env python3
"""Training-only audit of repeated-source track support and profiled CFOs."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.special import logsumexp


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent.parent / "2026_09_30_ds11_single10"
SOURCE_BALANCE = HERE.parent / "source_balance"
LANE_OFFSET = HERE.parent.parent / "2026_09_29_lane_offset_transfer"
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as fast  # noqa: E402


REFERENCE_RF_HZ = 11.2e9
NATIVE_ALIAS_PERIOD_HZ = 1.0 / 4.4e-6
CONFIDENCE_THRESHOLD = 0.90


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def alias_wrapped_difference_hz(a: float, b: float) -> float:
    """Signed minimum native-frequency difference under the GLRT alias period."""
    return float((a - b + NATIVE_ALIAS_PERIOD_HZ / 2) % NATIVE_ALIAS_PERIOD_HZ
                 - NATIVE_ALIAS_PERIOD_HZ / 2)


def classify_support(a: dict, b: dict) -> dict:
    shared = sorted(set(a["training_visits"]) & set(b["training_visits"]))
    start = max(a["start_s"], b["start_s"])
    end = min(a["end_s"], b["end_s"])
    span = max(a["end_s"], b["end_s"]) - min(a["start_s"], b["start_s"])
    if shared:
        category = "shared_visit"
        gap = 0.0
        overlap = max(0.0, end - start)
    elif end >= start:
        category = "interval_overlap_no_shared_visit"
        gap = 0.0
        overlap = end - start
    else:
        category = "disjoint"
        gap = start - end
        overlap = 0.0
    union = set(a["training_visits"]) | set(b["training_visits"])
    return {
        "support": category,
        "shared_training_visits": len(shared),
        "visit_jaccard": len(shared) / len(union),
        "gap_s": float(gap),
        "overlap_s": float(overlap),
        "combined_span_s": float(span),
        "same_channel": a["channel"] == b["channel"],
        "identical_training_visits": a["training_visits"] == b["training_visits"],
    }


def make_pair(a: dict, b: dict, kind: str) -> dict:
    row = {
        "kind": kind,
        "scan_index": a["scan_index"],
        "session_id": a["session_id"],
        "rf_hz": a["rf_hz"],
        "receiver_a": a["receiver_id"],
        "receiver_b": b["receiver_id"],
        "norad_a": a["norad"],
        "norad_b": b["norad"],
        "track_a": a["track_id"],
        "track_b": b["track_id"],
    }
    row.update(classify_support(a, b))
    signed = alias_wrapped_difference_hz(a["native_cfo_hz"], b["native_cfo_hz"])
    row["native_cfo_difference_hz"] = signed
    row["absolute_native_cfo_difference_hz"] = abs(signed)
    return row


def summarize(values) -> dict:
    values = np.asarray(list(values), dtype=float)
    if not len(values):
        return {"count": 0, "median": None, "p90": None, "p99": None}
    return {
        "count": int(len(values)),
        "median": float(np.median(values)),
        "p90": float(np.quantile(values, 0.90)),
        "p99": float(np.quantile(values, 0.99)),
    }


def match_control(target: dict, controls: list[dict]) -> dict | None:
    compatible = [row for row in controls if row["support"] == target["support"]]
    if not compatible:
        return None
    def key(row):
        return (
            abs(row["gap_s"] - target["gap_s"]),
            abs(row["overlap_s"] - target["overlap_s"]),
            abs(row["combined_span_s"] - target["combined_span_s"]),
            row["track_a"],
            row["track_b"],
        )
    return min(compatible, key=key)


def verify_plan(plan: dict) -> None:
    for entry in plan["inputs"]:
        for artifact in entry["artifacts"]:
            actual = digest(Path(artifact["path"]))
            expected = artifact["sha256"]
            if actual != expected:
                raise ValueError(f"plan artifact digest mismatch: {artifact['path']}")


def selected_tracks() -> tuple[list[dict], dict]:
    plan_path = BASE / "plan.json"
    sidecar_path = SOURCE_BALANCE / "catalogue_identities.json"
    plan = json.loads(plan_path.read_text())
    sidecar = json.loads(sidecar_path.read_text())
    if sidecar.get("schema") != "ds11-source-balance-identities/v1":
        raise ValueError("identity sidecar schema mismatch")
    if sidecar.get("plan_sha256") != digest(plan_path).removeprefix("sha256:"):
        raise ValueError("identity sidecar plan binding mismatch")
    verify_plan(plan)

    rows = []
    result_paths = []
    duplicate_candidate_norad_tracks = 0
    for index, entry in enumerate(plan["inputs"]):
        result_path = BASE / "runs" / f"{index:02d}_iid.json"
        result = json.loads(result_path.read_text())
        selected = result.get("selected")
        if not selected or not selected.get("qualified"):
            raise ValueError(f"original IID endpoint {index} is not qualified")
        request = {"config": plan["config"], "inputs": [entry]}
        document = fast.load_documents(request)[0]
        identity = sidecar["scans"][str(index)]
        if document["session_id"] != identity["session_id"]:
            raise ValueError(f"identity session mismatch at index {index}")
        engine = fast.baseline.Stationary(document, plan["config"])
        local = np.asarray(selected["x"], dtype=float)
        if local.shape != (3,):
            raise ValueError(f"unexpected original IID endpoint dimension at {index}")
        for track in document["tracks"]:
            candidate_norad = identity["tracks"][track["track_id"]]["candidate_norad"]
            duplicate_candidate_norad_tracks += len(candidate_norad) != len(set(candidate_norad))
            prediction, visible = engine.prediction(track, local)
            score, _, audits, offsets = fast.profile(
                track["y"][None, :] - prediction, track["mask"]
            )
            if not all(audit["converged"] for audit in audits):
                raise RuntimeError(f"CFO profiler stationarity failure at {index}")
            score = np.where(visible, score, -np.inf)
            normal = logsumexp(score)
            if not math.isfinite(float(normal)):
                raise ValueError(f"no visible candidate at {index}")
            probabilities = np.exp(score - normal)
            slot = int(np.argmax(probabilities))
            mask = np.asarray(track["mask"], dtype=bool)
            times = np.asarray(track["times_s"], dtype=float)[mask]
            visits = np.asarray(track["visits"])[mask]
            if not len(times):
                raise ValueError("track has no training observations")
            cfo = float(offsets[slot])
            rows.append({
                "scan_index": index,
                "session_id": document["session_id"],
                "track_id": track["track_id"],
                "receiver_id": int(track["receiver_id"]),
                "channel": int(track["channel"]),
                "rf_hz": float(track["rf_hz"]),
                "norad": int(candidate_norad[slot]),
                "confidence": float(probabilities[slot]),
                "unambiguous": float(probabilities[slot]) >= CONFIDENCE_THRESHOLD,
                "canonical_cfo_hz": cfo,
                "native_cfo_hz": cfo * float(track["rf_hz"]) / REFERENCE_RF_HZ,
                "training_observations": int(mask.sum()),
                "training_visits": [int(value) for value in visits],
                "start_s": float(times.min()),
                "end_s": float(times.max()),
            })
        result_paths.append(result_path)
    sources = {
        "plan": {"path": str(plan_path), "sha256": digest(plan_path)},
        "identity_sidecar": {"path": str(sidecar_path), "sha256": digest(sidecar_path)},
        "fast_adapter": {
            "path": str(ROOT / "tools" / "ds7_fast_baseline_adapter.py"),
            "sha256": digest(ROOT / "tools" / "ds7_fast_baseline_adapter.py"),
        },
        "baseline_adapter": {
            "path": str(ROOT / "tools" / "ds7_baseline_adapter.py"),
            "sha256": digest(ROOT / "tools" / "ds7_baseline_adapter.py"),
        },
        "prior_lane_offset_model": {
            "path": str(LANE_OFFSET / "model.py"), "sha256": digest(LANE_OFFSET / "model.py")
        },
        "prior_lane_offset_protocol": {
            "path": str(LANE_OFFSET / "PROTOCOL.md"), "sha256": digest(LANE_OFFSET / "PROTOCOL.md")
        },
        "original_iid_results": [
            {"path": str(path), "sha256": digest(path)} for path in result_paths
        ],
    }
    return rows, {"sources": sources, "duplicate_candidate_norad_tracks": duplicate_candidate_norad_tracks}


def grouped_pairs(tracks: list[dict]) -> tuple[list[dict], list[dict], list[dict], dict]:
    eligible = [row for row in tracks if row["unambiguous"]]
    same_receiver_groups = defaultdict(list)
    same_source_groups = defaultdict(list)
    lane_groups = defaultdict(list)
    for row in eligible:
        same_receiver_groups[(row["scan_index"], row["norad"], row["rf_hz"], row["receiver_id"])].append(row)
        same_source_groups[(row["scan_index"], row["norad"], row["rf_hz"])].append(row)
        lane_groups[(row["scan_index"], row["rf_hz"], row["receiver_id"])].append(row)

    same_rx = []
    group_categories = Counter()
    for group in same_receiver_groups.values():
        if len(group) < 2:
            continue
        pairs = [make_pair(a, b, "same_source_same_receiver")
                 for a, b in itertools.combinations(sorted(group, key=lambda x: x["track_id"]), 2)]
        same_rx.extend(pairs)
        categories = {row["support"] for row in pairs}
        group_categories["repeated"] += 1
        group_categories["all_pairs_disjoint"] += categories == {"disjoint"}
        for category in categories:
            group_categories[f"any_{category}"] += 1

    cross_rx = []
    for group in same_source_groups.values():
        for a, b in itertools.combinations(sorted(group, key=lambda x: x["track_id"]), 2):
            if a["receiver_id"] != b["receiver_id"]:
                cross_rx.append(make_pair(a, b, "same_source_cross_receiver"))

    controls = []
    for group in lane_groups.values():
        for a, b in itertools.combinations(sorted(group, key=lambda x: x["track_id"]), 2):
            if a["norad"] != b["norad"]:
                controls.append(make_pair(a, b, "different_source_same_receiver_control"))
    return same_rx, cross_rx, controls, dict(group_categories)


def category_summary(rows: list[dict]) -> dict:
    answer = {}
    for category in ("shared_visit", "interval_overlap_no_shared_visit", "disjoint"):
        subset = [row for row in rows if row["support"] == category]
        answer[category] = {
            "pairs": len(subset),
            "absolute_native_cfo_difference_hz": summarize(
                row["absolute_native_cfo_difference_hz"] for row in subset
            ),
            "gap_s": summarize(row["gap_s"] for row in subset if row["gap_s"] > 0),
            "combined_span_s": summarize(row["combined_span_s"] for row in subset),
            "same_channel_pairs": sum(row["same_channel"] for row in subset),
            "identical_training_visit_pairs": sum(row["identical_training_visits"] for row in subset),
        }
    return answer


def build_output() -> dict:
    tracks, provenance = selected_tracks()
    same_rx, cross_rx, controls, group_categories = grouped_pairs(tracks)
    matched = []
    for target in same_rx:
        lane_controls = [row for row in controls
                         if row["scan_index"] == target["scan_index"]
                         and row["rf_hz"] == target["rf_hz"]
                         and row["receiver_a"] == target["receiver_a"]]
        control = match_control(target, lane_controls)
        row = dict(target)
        if control is None:
            row["matched_control"] = None
        else:
            row["matched_control"] = {
                "track_a": control["track_a"],
                "track_b": control["track_b"],
                "norad_a": control["norad_a"],
                "norad_b": control["norad_b"],
                "absolute_native_cfo_difference_hz": control["absolute_native_cfo_difference_hz"],
                "gap_s": control["gap_s"],
                "overlap_s": control["overlap_s"],
                "combined_span_s": control["combined_span_s"],
            }
        matched.append(row)
    available = [row for row in matched if row["matched_control"] is not None]
    paired_delta = [row["matched_control"]["absolute_native_cfo_difference_hz"]
                    - row["absolute_native_cfo_difference_hz"] for row in available]
    script_path = Path(__file__).resolve()
    return {
        "schema": "ds11-same-source-cfo-audit/v1",
        "method": {
            "data": "original32 qualified IID endpoints; training observations only",
            "identity": "training-MAP NORAD conditional on posterior >= 0.90, exact RF",
            "same_oscillator_group": "scan, selected NORAD, exact RF Hz, receiver",
            "cross_receiver_policy": "reported separately because receiver oscillators differ",
            "cfo": "original t4 scale100 per-track profile at frozen IID endpoint and training-MAP candidate",
            "alias": {
                "native_period_hz": NATIVE_ALIAS_PERIOD_HZ,
                "normalization": "canonical CFO * exact RF / 11.2 GHz, then minimum circular difference",
            },
            "support": "shared training visit; else overlapping time intervals; else disjoint",
            "control": "same scan/receiver/exact RF but different selected NORAD, same support class; nearest geometry with deterministic tie-break; matching with replacement",
            "prohibited_inputs": "no reference position/error and no held-out observation used",
        },
        "counts": {
            "tracks": len(tracks),
            "unambiguous_tracks": sum(row["unambiguous"] for row in tracks),
            "ambiguous_tracks_excluded_from_identity_pairs": sum(not row["unambiguous"] for row in tracks),
            "duplicate_candidate_norad_tracks": provenance["duplicate_candidate_norad_tracks"],
            "same_source_same_receiver_groups": group_categories,
            "same_source_same_receiver_pairs": len(same_rx),
            "same_source_cross_receiver_pairs": len(cross_rx),
            "different_source_same_receiver_control_population_pairs": len(controls),
            "same_receiver_pairs_with_matched_control": len(available),
        },
        "same_source_same_receiver": category_summary(same_rx),
        "same_source_cross_receiver": category_summary(cross_rx),
        "different_source_same_receiver_controls": category_summary(controls),
        "matched_comparison": {
            "pairs": len(available),
            "within_source_smaller_count": sum(value > 0 for value in paired_delta),
            "ties": sum(value == 0 for value in paired_delta),
            "control_minus_within_absolute_cfo_hz": summarize(paired_delta),
            "within_absolute_cfo_hz": summarize(
                row["absolute_native_cfo_difference_hz"] for row in available
            ),
            "control_absolute_cfo_hz": summarize(
                row["matched_control"]["absolute_native_cfo_difference_hz"] for row in available
            ),
        },
        "track_rows": tracks,
        "same_receiver_pair_rows": matched,
        "cross_receiver_pair_rows": cross_rx,
        "source_sha256": {
            **provenance["sources"],
            "audit_script": {"path": str(script_path), "sha256": digest(script_path)},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_output()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
