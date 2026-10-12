"""Frozen nested curve comparison for every pinned DS20/DS16 component."""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from band_calibrated_merge_study import REPORT, ROOT
from continuous_merge_positions import load_prepared
from continuous_merge_study import sha, write

from leo.analysis.cfo_lines import CfoPoint
from leo.analysis.continuous_track_merge import TrackSeries
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories
from leo.analysis.predictive_merge_curves import (
    PredictiveCurveConfiguration,
    compare_predictive_curves,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
from leo.scanner.persistent_hop import Feature103DualRxTimingV3, PersistentHopUtcTimingAuthorityV1

ORIGINAL = Path("/srv/bulk/leo-dev/leo-track-merge-study/reports/2026_10_12_continuous_track_merge")
OUTPUT = REPORT / "local/predictive-curves"


def freeze():
    path = OUTPUT / "protocol.json"
    if path.exists():
        raise ValueError("predictive protocol already frozen")
    membership = json.loads((ORIGINAL / "membership.json").read_bytes())
    cases = []
    for member in membership["members"]:
        old = ORIGINAL / "local" / member["dataset"] / member["session_id"]
        bindings = {
            str(old / name): sha(old / name)
            for name in ("baseline.json", "source.json", "census.json")
        }
        cases.append({**member, "original_case": str(old), "bindings": bindings})
    paths = [
        Path(__file__),
        ORIGINAL / "membership.json",
        ROOT / "tools/continuous_merge_positions.py",
        ROOT / "tools/continuous_merge_study.py",
        ROOT / "src/leo/analysis/predictive_merge_curves.py",
        ROOT / "src/leo/analysis/persistent_hop_trajectory.py",
        ROOT / "src/leo/application/scanner_trajectory.py",
    ]
    write(
        path,
        {
            "cases": cases,
            "bindings": {str(p): sha(p) for p in paths},
            "configuration": asdict(PredictiveCurveConfiguration()),
            "reference_usage": "none in freeze or execute",
            "scope": (
                "All existing 81 census recordings and every final guarded multi-parent component. "
                "Membership, passing GLRT selection and fixed GLRT weights are conditioned upon; "
                "they are not independent outer-held-out discoveries. Raw normalized CFO enters "
                "training-only unwrapping/alias alignment. Outer5fold/inner3fold repeats use random "
                "whole2s blocks compare joined versus separate curves (one common selected degree "
                "across separate parents). No orbit bank, c term, position fit or reference. "
                "Existing whole-recording development/validation roles remain unchanged."
            ),
        },
    )
    print(json.dumps({"cases": len(cases), "protocol_sha256": sha(path)}), flush=True)


def verify(bindings):
    for path, digest in bindings.items():
        if sha(Path(path)) != digest:
            raise ValueError("predictive authority changed: " + path)


def series_for(old, prepared):
    data = json.loads((old / "source.json").read_bytes())
    timing_type = {1: PersistentHopUtcTimingAuthorityV1, 3: Feature103DualRxTimingV3}[
        data["timing"]["schema_version"]
    ]
    data["timing"] = timing_type.model_validate(data["timing"])
    data["probes"] = tuple(
        TrackingProbe(**{**p, "candidates": tuple(TrackingCandidate(**c) for c in p["candidates"])})
        for p in data["probes"]
    )
    candidates = {c.candidate_id: c for c in project_scanner_candidates(TrackingInput(**data))}
    trajectory = reconstruct_persistent_hop_trajectories(
        tuple(candidates[c] for c in prepared.candidate_ids)
    )
    result = {}
    for track in trajectory.tracklets:
        points = sorted(
            track.points, key=lambda p: candidates[p.candidate_id].support_center_utc_ns
        )
        exact = [candidates[p.candidate_id] for p in points]
        result[track.tracklet_id] = TrackSeries(
            (track.tracklet_id,),
            track.lane_key,
            tuple(p.candidate_id for p in points),
            tuple(c.source_group_id for c in exact),
            np.array([(c.support_center_utc_ns - prepared.start_utc_ns) / 1e9 for c in exact]),
            np.array([p.normalized_raw_cfo_hz for p in points]),
            np.array(
                [
                    CfoPoint(c.candidate_id, 0, 0, c.exact_score, c.control_score, c.margin).weight
                    for c in exact
                ]
            ),
            (1 / 4.4e-6) * trajectory.canonical_rf_hz / track.lane_key[3],
        )
    return result


def execute(limit, maximum_seconds):
    path = OUTPUT / "protocol.json"
    protocol = json.loads(path.read_bytes())
    verify(protocol["bindings"])
    config = PredictiveCurveConfiguration(
        **{**protocol["configuration"], "degrees": tuple(protocol["configuration"]["degrees"])}
    )
    started, completed = time.monotonic(), 0
    for case in protocol["cases"]:
        destination = OUTPUT / case["dataset"] / (case["session_id"] + ".json")
        if destination.exists():
            continue
        if completed >= limit or time.monotonic() - started > maximum_seconds - 30:
            break
        verify(case["bindings"])
        old = Path(case["original_case"])
        prepared = load_prepared(old / "baseline.json")
        inventory = series_for(old, prepared)
        components = json.loads((old / "census.json").read_bytes())["variants"]["replace-guard"][
            "components"
        ]
        rows = []
        for component in components:
            record = {"component": component, "status": "failed", "reason": None}
            try:
                record["comparison"] = compare_predictive_curves(
                    [inventory[identity] for identity in component["member_ids"]], config
                )
                record["status"] = "complete"
            except ValueError as error:
                record["reason"] = str(error)
            rows.append(record)
        write(
            destination,
            {
                "dataset": case["dataset"],
                "session_id": case["session_id"],
                "role": case["role"],
                "protocol_sha256": sha(path),
                "reference_usage": "none",
                "rows": rows,
            },
        )
        completed += 1
        print(
            json.dumps(
                {
                    "dataset": case["dataset"],
                    "session_id": case["session_id"],
                    "components": len(rows),
                    "failures": sum(r["status"] != "complete" for r in rows),
                }
            ),
            flush=True,
        )
    print(
        json.dumps({"completed_this_slice": completed, "elapsed_s": time.monotonic() - started}),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "execute"))
    parser.add_argument("--limit", type=int, default=81)
    parser.add_argument("--maximum-seconds", type=float, default=600)
    args = parser.parse_args()
    if args.operation == "freeze":
        freeze()
    else:
        execute(args.limit, args.maximum_seconds)
