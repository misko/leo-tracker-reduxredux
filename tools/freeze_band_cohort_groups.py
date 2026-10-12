"""Freeze expanded group studies using explicit original-segment authority."""

import argparse
import json
from pathlib import Path

import numpy as np
from band_calibrated_merge_study import PREVIOUS, ROOT
from continuous_merge_positions import load_prepared
from continuous_merge_study import sha, write
from shared_track_refinement_study import ARMS, VARIANTS, restore

from leo.analysis.continuous_merge_groups import continuous_mark_groups
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.regional_position import PositionOrbitBank
from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
from leo.scanner.persistent_hop import Feature103DualRxTimingV3, PersistentHopUtcTimingAuthorityV1


def freeze(dataset, sid):
    case = PREVIOUS / "local" / dataset / sid
    output = case / "shared-refinement/protocol.json"
    if output.exists():
        raise ValueError("shared group protocol already exists; never overwrite it")
    parent_path = case / "positions/experiment.json"
    parent = json.loads(parent_path.read_bytes())
    for path, digest in {**parent["source_bindings"], **parent["input_bindings"]}.items():
        if sha(Path(path)) != digest:
            raise ValueError("parent authority changed: " + path)
    old = Path(parent["original_case"])
    prepared, merged = (
        load_prepared(old / "baseline.json"),
        load_prepared(old / "replace-guard.json"),
    )
    terminal_path = case / "positions/baseline/terminal.json"
    terminal = json.loads(terminal_path.read_bytes())
    if terminal["status"] != "complete":
        raise ValueError("stationary baseline required")
    final = next(f for f in terminal["result"]["finals"] if f["arm"] == "fitted-c")
    if final["accepted_stage"] != "B7" or not final["fit"]["converged"]:
        raise ValueError("stationary B7 seed required")
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
    lookup = {identity: i for i, identity in enumerate(prepared.candidate_ids)}
    tracks = {
        t.tracklet_id: tuple(lookup[p.candidate_id] for p in t.points) for t in trajectory.tracklets
    }
    components = json.loads((old / "census.json").read_bytes())["variants"]["replace-guard"][
        "components"
    ]
    groups, audit = continuous_mark_groups(
        prepared.bootstrap_tracks,
        merged.bootstrap_tracks,
        tracks,
        [c["member_ids"] for c in components],
    )
    for grouping in groups.values():
        for rows in grouping:
            if len(np.unique(prepared.observations.rf_hz[list(rows)])) != 1:
                raise ValueError("cross-RF groups not authorized")
    with np.load(case / "positions/bank.npz") as z:
        bank = PositionOrbitBank(**{key: z[key] for key in z.files})
    restore(prepared, bank, final, groups["joined"], 0.0)
    paths = [
        old / name for name in ("baseline.json", "replace-guard.json", "source.json", "census.json")
    ]
    paths += [
        parent_path,
        terminal_path,
        case / "positions/bank.npz",
        Path(__file__),
        ROOT / "tools/shared_track_refinement_study.py",
        ROOT / "src/leo/analysis/continuous_merge_groups.py",
        ROOT / "src/leo/analysis/shared_track_likelihood.py",
        ROOT / "src/leo/analysis/shared_track_objective.py",
    ]
    write(
        output,
        {
            "dataset": dataset,
            "session_id": sid,
            "role": parent["role"],
            "baseline_protocol": str(parent_path),
            "original_case": str(old),
            "bindings": {str(path): sha(path) for path in paths},
            "groups": groups,
            "excluded_ambiguous_rows": audit["excluded_ambiguous_rows"],
            "group_authority_audit": audit,
            "variants": VARIANTS,
            "arms": ARMS,
            "maximum_seconds": 90,
            "maximum_iterations": 600,
            "source_satellites": final["satellites"],
            "reference_usage": "none in freeze/execute",
            "scope": (
                "Same frozen local B7 experiment; distinguish actual explicit joined components "
                "from original segments newly admitted by the changed bootstrap quota. All "
                "original "
                "observations remain scored; ungrouped and ambiguous rows remain independent. "
                "Full original segment inventory supplies parent authority. No reference used."
            ),
        },
    )
    print(
        json.dumps(
            {
                "joined_groups": len(groups["joined"]),
                "parent_groups": len(groups["parents"]),
                **audit,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=("DS20", "DS16"))
    parser.add_argument("session_id")
    args = parser.parse_args()
    freeze(args.dataset, args.session_id)
