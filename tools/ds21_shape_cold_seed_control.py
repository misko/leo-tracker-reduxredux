"""Matched enlarged-bank cold seeds: no shape geographic initialization."""

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from leo.analysis.channel_group_seeds import shared_bootstrap_seed
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_bootstrap import PositionBootstrap, bootstrap_position
from leo.analysis.regional_position_score import zero_sum_basis
from leo.application.channel_group_refinement import objective


def fixed_pool_bootstrap(observations, full_bank, prior, point, tracks, full_indices):
    """The bootstrap sees only the predeclared enlarged pool; indices map back."""
    subset = full_bank.select(list(full_indices))
    result = bootstrap_position(
        observations,
        subset,
        prior,
        point,
        tracks,
        maximum_seconds=5.0,
        orbit_predictor=predict_orbits,
    )
    return PositionBootstrap(
        tuple(full_indices[i] for i in result.satellite_indices),
        result.vector,
        tuple(
            replace(match, satellite_index=full_indices[match.satellite_index])
            for match in result.matches
        ),
    )


def run(label):
    from ds21_common import OUTPUT, digest, immutable, load_case

    case = load_case(label)
    parent = OUTPUT / "local/model-b-shape-fresh-absolute-hybrid-v3" / label
    pool = json.loads((parent / "candidate-pool.json").read_bytes())
    indices = tuple(pool["candidate_full_indices"])
    bank = case["full_bank"].select(list(indices))
    if bank.numbers.tolist() != pool["candidate_numbers"]:
        raise ValueError("Fixed enlarged bank differs from parent")
    directory = OUTPUT / "local/cold-start-control-v1" / label
    proposals = [
        {"start": i, "point_km": [row["east_km"], row["north_km"]]}
        for i, row in enumerate(case["discovery"]["selected"])
    ]
    source_root = Path(__file__).parents[1]
    paths = [
        Path(__file__),
        source_root / "src/leo/analysis/regional_position_bootstrap.py",
        source_root / "src/leo/analysis/channel_group_seeds.py",
        source_root / "src/leo/application/channel_group_refinement.py",
    ]
    snapshots = {}
    for source in paths:
        target = directory / "source-snapshot" / source.name
        value = source.read_bytes()
        if target.exists() and target.read_bytes() != value:
            raise ValueError(f"Cold-control source changed: {source.name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
        snapshots[source.name] = digest(target)
    protocol = {
        "label": label,
        "model": "fixed-enlarged-bank-original-cold-start-control",
        "parent_v3_terminal_sha256": digest(parent / "terminal.json"),
        "parent_candidate_pool_sha256": digest(parent / "candidate-pool.json"),
        "candidate_full_indices": indices,
        "candidate_numbers": bank.numbers.tolist(),
        "common_protocol_sha256": case["protocol_sha256"],
        "prepared_sha256": {k: p.evidence_sha256 for k, p in case["prepared"].items()},
        "proposals": proposals,
        "source_snapshots": snapshots,
        "bootstrap_seconds_per_view": 5.0,
        "bootstrap_views_per_point": 3,
        "candidate_additions": False,
        "timing_fallback": "nearest frozen v3 all-view training seed",
        "reference_usage": "none",
        "held_usage": "none",
    }
    immutable(directory / "protocol.json", protocol)
    immutable(
        directory / "candidate-pool.json",
        {
            "candidate_full_indices": indices,
            "candidate_numbers": bank.numbers.tolist(),
            "proposals": proposals,
        },
    )
    v3_seeds = json.loads((parent / "seeds/all.json").read_bytes())
    seeds = {view: [] for view in case["prepared"]}
    for index, proposal in enumerate(proposals):
        path = directory / "bootstrap" / f"proposal-{index}.json"
        if path.exists():
            receipt = json.loads(path.read_bytes())
        else:
            receipt = {"point_km": proposal["point_km"], "hypotheses": {}, "failures": {}}
            for view, prepared in case["prepared"].items():
                try:
                    value = fixed_pool_bootstrap(
                        prepared.observations,
                        case["full_bank"],
                        case["prior"],
                        proposal["point_km"],
                        prepared.bootstrap_tracks,
                        indices,
                    )
                    receipt["hypotheses"][view] = asdict(value)
                except (ValueError, TimeoutError) as error:
                    receipt["failures"][view] = str(error)
            immutable(path, receipt)
        if not receipt["hypotheses"]:
            raise ValueError(f"No cold bootstrap at original discovery start {index}")
        hypotheses = {
            view: (
                PositionBootstrap(
                    tuple(value["satellite_indices"]), np.asarray(value["vector"]), ()
                ),
                case["prepared"][view].observations,
            )
            for view, value in receipt["hypotheses"].items()
        }
        nearest = min(
            v3_seeds,
            key=lambda s: float(np.sum((np.asarray(s["vector"][:2]) - proposal["point_km"]) ** 2)),
        )
        vector = np.asarray(nearest["vector"])
        shifts = vector[7] + zero_sum_basis(len(indices)) @ vector[8:]
        fallback = dict(zip(indices, shifts, strict=True))
        for view, prepared in case["prepared"].items():
            model = objective(prepared, bank, case["prior"], case["nodes"])
            seeds[view].append(
                shared_bootstrap_seed(model, indices, hypotheses, fallback_timings=fallback)
            )
    bindings = {}
    for view, values in seeds.items():
        path = directory / "seeds" / f"{view}.json"
        immutable(path, values)
        bindings[view] = digest(path)
    immutable(
        directory / "terminal.json",
        {
            "state": "complete",
            "label": label,
            "protocol_sha256": digest(directory / "protocol.json"),
            "seed_sha256": bindings,
            "reference_usage": "none",
        },
    )
    print(
        json.dumps({"label": label, "state": "complete", "directory": str(directory)}), flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    run(parser.parse_args().label)
