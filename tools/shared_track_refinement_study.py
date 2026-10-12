"""Frozen local B7 refinements with independent, parent, and joined mark models."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from continuous_merge_consistency_study import LOCAL
from continuous_merge_positions import load_prepared
from continuous_merge_study import plain, sha, write

from leo.analysis.hard60_dynamic_rf import fit
from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories
from leo.analysis.regional_position_score import coordinates
from leo.analysis.shared_track_likelihood import shared_track_terms
from leo.analysis.shared_track_objective import SharedTrackObjective
from leo.application.hard60_runner import HARD60_SCORE
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior
from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
from leo.scanner.persistent_hop import Feature103DualRxTimingV3, PersistentHopUtcTimingAuthorityV1

VARIANTS = {
    "independent": ("joined", 0.0),
    "parents": ("parents", 0.5),
    "joined": ("joined", 0.5),
    "forced": ("joined", 1.0),
}
ARMS = ("fitted-c", "zero-c")


def restore(prepared, bank, final, groups, shared_prior):
    state = final["fit"]["joint_state"]
    nodes, knots = np.array(state["clock_nodes_s"]), np.array(state["clock_knots_hz"])
    obs = prepared.observations
    interpolation = np.column_stack(
        [np.interp(obs.times_s, nodes, row) for row in np.eye(len(nodes))]
    )
    original_clock_values = np.sum(interpolation * knots[obs.receiver], axis=1)
    lookup = {int(n): i for i, n in enumerate(bank.numbers)}
    base = Hard60Objective(
        obs,
        bank.select([lookup[n] for n in final["satellites"]]),
        RegionalPrior(),
        HARD60_SCORE,
        receiver_baseline_hz=np.array(state["receiver_baseline_hz"]) + original_clock_values,
    )
    model = SharedTrackObjective(
        base,
        nodes,
        knots,
        np.array(state["satellite_centers_s"]),
        groups,
        shared_prior=shared_prior,
    )
    vector, clock = np.array(state["vector"]), np.array(state["clock_coefficients"])
    control = SharedTrackObjective(
        base, nodes, knots, np.array(state["satellite_centers_s"]), groups, shared_prior=0.0
    )
    value, _, _, terms = control.evaluate_joint(vector, clock)
    if (
        abs(value - state["total_objective"]) > 1e-6
        or abs(terms.nll - state["likelihood_nll"]) > 1e-6
    ):
        raise ValueError("saved B7 model could not be reproduced")
    return model, vector, clock


def freeze(case):
    output = case / "shared-refinement"
    if (output / "protocol.json").exists():
        raise ValueError("shared refinement protocol already exists")
    parent = json.loads((case / "positions/experiment.json").read_bytes())
    old = Path(parent["original_case"])
    prepared, merged = (
        load_prepared(old / "baseline.json"),
        load_prepared(old / "replace-guard.json"),
    )
    terminal = json.loads((case / "positions/baseline/terminal.json").read_bytes())
    if terminal["status"] != "complete":
        raise ValueError("completed reference-free baseline required")
    final = next(f for f in terminal["result"]["finals"] if f["arm"] == "fitted-c")
    if final["accepted_stage"] != "B7" or not final["fit"]["converged"]:
        raise ValueError("this study requires a stationary B7 seed")
    d = json.loads((old / "source.json").read_bytes())
    timing_types = {1: PersistentHopUtcTimingAuthorityV1, 3: Feature103DualRxTimingV3}
    timing_type = timing_types[d["timing"]["schema_version"]]
    d["timing"] = timing_type.model_validate(d["timing"])
    d["probes"] = tuple(
        TrackingProbe(**{**p, "candidates": tuple(TrackingCandidate(**c) for c in p["candidates"])})
        for p in d["probes"]
    )
    source = TrackingInput(**d)
    candidates = {c.candidate_id: c for c in project_scanner_candidates(source)}
    trajectory = reconstruct_persistent_hop_trajectories(
        tuple(candidates[i] for i in prepared.candidate_ids)
    )
    lookup = {identity: i for i, identity in enumerate(prepared.candidate_ids)}
    tracks = {
        t.tracklet_id: set(lookup[p.candidate_id] for p in t.points) for t in trajectory.tracklets
    }
    components = json.loads((old / "census.json").read_bytes())["variants"]["replace-guard"][
        "components"
    ]
    originals = set(prepared.bootstrap_tracks)
    joins, parents = [], []
    for rows in merged.bootstrap_tracks:
        if rows in originals:
            continue
        matching = [
            c for c in components if set().union(*(tracks[t] for t in c["member_ids"])) == set(rows)
        ]
        if len(matching) != 1:
            raise ValueError("joined proposal has ambiguous parent authority")
        joins.append(set(rows))
        parents.extend(tracks[t] for t in matching[0]["member_ids"])
    counts = {}
    for rows in parents:
        for row in rows:
            counts[row] = counts.get(row, 0) + 1
    ambiguous = {row for row, count in counts.items() if count > 1}
    groups = {
        "joined": [tuple(sorted(r - ambiguous)) for r in joins if r - ambiguous],
        "parents": [tuple(sorted(r - ambiguous)) for r in parents if r - ambiguous],
    }
    assert set().union(*map(set, groups["joined"])) == set().union(*map(set, groups["parents"]))
    with np.load(case / "positions/bank.npz") as z:
        bank = PositionOrbitBank(**{k: z[k] for k in z.files})
    for grouping in groups.values():
        for rows in grouping:
            if len(np.unique(prepared.observations.rf_hz[list(rows)])) != 1:
                raise ValueError("cross-RF group not authorized by this experiment")
    restore(prepared, bank, final, groups["joined"], 0.0)
    paths = [
        old / "baseline.json",
        old / "replace-guard.json",
        old / "source.json",
        old / "census.json",
        case / "positions/baseline/terminal.json",
        case / "positions/bank.npz",
        Path(__file__),
        Path(__file__).parents[1] / "src/leo/analysis/shared_track_likelihood.py",
        Path(__file__).parents[1] / "src/leo/analysis/shared_track_objective.py",
    ]
    protocol = {
        "dataset": parent["dataset"],
        "session_id": parent["session_id"],
        "role": parent["role"],
        "baseline_protocol": str(case / "positions/experiment.json"),
        "original_case": str(old),
        "bindings": {str(p): sha(p) for p in paths},
        "groups": groups,
        "excluded_ambiguous_rows": sorted(ambiguous),
        "variants": VARIANTS,
        "arms": ARMS,
        "maximum_seconds": 90,
        "maximum_iterations": 600,
        "source_satellites": final["satellites"],
        "reference_usage": "none in freeze/execute",
        "scope": (
            "Conditional local refinement from one common data-selected fitted-c B7 seed. "
            "All variants and c arms share observations, candidate bank, receiver calibration, "
            "timing/slope/clock priors, geographic prior, seed, and 25 km local box. "
            "The original singleton count terms are retained; only mark correlation changes. "
            "Parent and joined structures cover identical original windows; ambiguous boundary "
            "rows remain independently scored. This is development evidence, not a full search "
            "or an independent validation result."
        ),
    }
    write(output / "protocol.json", protocol)
    print(
        json.dumps(
            {
                "joined_groups": len(groups["joined"]),
                "parent_groups": len(groups["parents"]),
                "grouped_windows": len(set().union(*map(set, groups["joined"]))),
                "ambiguous_rows": len(ambiguous),
            }
        )
    )


def execute(case, variant, arm):
    output = case / "shared-refinement"
    p = json.loads((output / "protocol.json").read_bytes())
    for path, digest in p["bindings"].items():
        if sha(Path(path)) != digest:
            raise ValueError("bound shared-refinement authority changed: " + path)
    baseline = json.loads(Path(p["baseline_protocol"]).read_bytes())
    for path, digest in baseline["source_bindings"].items():
        if sha(Path(path)) != digest:
            raise ValueError("bound baseline source changed")
    path = output / (variant + "-" + arm + ".json")
    if path.exists():
        print("already recorded")
        return
    prepared = load_prepared(Path(p["original_case"]) / "baseline.json")
    terminal = json.loads((case / "positions/baseline/terminal.json").read_bytes())
    final = next(f for f in terminal["result"]["finals"] if f["arm"] == "fitted-c")
    with np.load(case / "positions/bank.npz") as z:
        bank = PositionOrbitBank(**{k: z[k] for k in z.files})
    grouping, prior = p["variants"][variant]
    model, vector, clock = restore(prepared, bank, final, p["groups"][grouping], prior)
    result = fit(
        model,
        vector,
        arm=arm,
        clock_seed=clock,
        maximum_seconds=p["maximum_seconds"],
        maximum_iterations=p["maximum_iterations"],
    )
    value, _, _, terms = model.evaluate_joint(result["vector"], result["clock_coefficients"])
    # Group evidence uses the unmodified singleton posterior at the fitted state.
    _, _, _, independent = super(SharedTrackObjective, model).evaluate_joint(
        result["vector"], result["clock_coefficients"]
    )
    _, evidence = shared_track_terms(independent, model.groups, shared_prior=prior)
    write(
        path,
        {
            "variant": variant,
            "arm": arm,
            "protocol_sha256": sha(output / "protocol.json"),
            "fit": plain(result),
            "objective": float(value),
            "frequency_nll": terms.nll,
            "groups": [
                {
                    "rows": e.rows,
                    "log_bayes_factor": e.log_bayes_factor,
                    "posterior_shared": e.posterior_shared,
                    "preferred_candidate": int(
                        model.bank.numbers[np.argmax(e.identity_probabilities)]
                    ),
                }
                for e in evidence
            ],
            "reference_usage": "none",
        },
    )
    print(
        json.dumps(
            {
                "variant": variant,
                "arm": arm,
                "stationary": result["converged"],
                "objective": value,
                "frequency_nll": terms.nll,
            }
        ),
        flush=True,
    )


def evaluate(case):
    output = case / "shared-refinement"
    files = [output / (v + "-" + a + ".json") for v in VARIANTS for a in ARMS]
    results = [json.loads(p.read_bytes()) for p in files]
    seal = {str(p): sha(p) for p in files}
    seal_path = output / "evaluation-seal.json"
    if seal_path.exists() and json.loads(seal_path.read_bytes()) != seal:
        raise ValueError("shared evaluation seal changed")
    write(seal_path, seal)
    # Use the already-sealed baseline comparison's evaluation reference only here.
    reference_authority = next((case / "positions").glob("evaluation-baseline-*.json"))
    reference = json.loads(reference_authority.read_bytes())["reference"]
    rows = []
    for r in results:
        latitude, longitude = coordinates(RegionalPrior(), r["fit"]["vector"][:2])
        lat, lon, ref_lat, ref_lon = map(math.radians, (latitude, longitude, *reference))
        h = (
            math.sin((lat - ref_lat) / 2) ** 2
            + math.cos(lat) * math.cos(ref_lat) * math.sin((lon - ref_lon) / 2) ** 2
        )
        rows.append(
            {
                "variant": r["variant"],
                "arm": r["arm"],
                "stationary": r["fit"]["converged"],
                "horizontal_error_m": 2 * 6371008.8 * math.asin(math.sqrt(min(1, max(0, h)))),
                "objective": r["objective"],
                "frequency_nll": r["frequency_nll"],
            }
        )
    write(
        output / "evaluation.json",
        {
            "seal_sha256": sha(seal_path),
            "rows": rows,
            "reference_authority_sha256": sha(reference_authority),
        },
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "execute", "evaluate"))
    parser.add_argument("dataset", choices=("DS20", "DS16"))
    parser.add_argument("session_id")
    parser.add_argument("--variant", choices=VARIANTS, default="joined")
    parser.add_argument("--arm", choices=ARMS, default="fitted-c")
    args = parser.parse_args()
    case = LOCAL / args.dataset / args.session_id
    if args.command == "freeze":
        freeze(case)
    elif args.command == "execute":
        execute(case, args.variant, args.arm)
    else:
        evaluate(case)
