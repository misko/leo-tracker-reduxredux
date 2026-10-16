"""Fresh training-only bootstrap pool at predetermined Model B proposals."""

from dataclasses import asdict

import numpy as np

from leo.analysis.channel_group_seeds import shared_bootstrap_seed
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_bootstrap import PositionBootstrap, bootstrap_position
from leo.analysis.regional_position_score import zero_sum_basis
from leo.application.channel_group_refinement import objective


def candidate_union(original, receipts, numbers):
    indices = set(original)
    for receipt in receipts:
        for hypothesis in receipt["hypotheses"].values():
            indices.update(hypothesis["satellite_indices"])
    return tuple(sorted(indices, key=lambda index: numbers[index]))


def fresh_seed_pool(case, proposals, directory):
    from ds21_common import immutable

    receipts = []
    for index, proposal in enumerate(proposals):
        path = directory / "bootstrap" / f"proposal-{index}.json"
        if path.exists():
            import json

            receipt = json.loads(path.read_bytes())
        else:
            receipt = {"point_km": proposal["point_km"], "hypotheses": {}, "failures": {}}
            for view, prepared in case["prepared"].items():
                try:
                    bootstrap = bootstrap_position(
                        prepared.observations,
                        case["full_bank"],
                        case["prior"],
                        proposal["point_km"],
                        prepared.bootstrap_tracks,
                        maximum_seconds=5.0,
                        orbit_predictor=predict_orbits,
                    )
                    receipt["hypotheses"][view] = asdict(bootstrap)
                except (ValueError, TimeoutError) as error:
                    receipt["failures"][view] = str(error)
            immutable(path, receipt)
        if not receipt["hypotheses"]:
            raise ValueError(f"No fresh bootstrap at shape proposal {index}")
        receipts.append(receipt)
    original = {i for r in case["discovery"]["selected"] for i in r["satellite_indices"]}
    indices = candidate_union(original, receipts, case["full_bank"].numbers)
    bank = case["full_bank"].select(list(indices))
    donors = []
    for receipt in receipts:
        for value in receipt["hypotheses"].values():
            vector = np.asarray(value["vector"])
            source_indices = value["satellite_indices"]
            shifts = vector[7] + zero_sum_basis(len(source_indices)) @ vector[8:]
            donors.append((receipt["point_km"], dict(zip(source_indices, shifts, strict=True))))
    for row in case["discovery"]["selected"]:
        for fit in row["fits"].values():
            if not fit.get("converged"):
                continue
            vector = np.asarray(fit["vector"])
            source_indices = row["satellite_indices"]
            shifts = vector[7] + zero_sum_basis(len(source_indices)) @ vector[8:]
            donors.append(
                ([row["east_km"], row["north_km"]], dict(zip(source_indices, shifts, strict=True)))
            )
    seeds = {view: [] for view in case["prepared"]}
    for receipt in receipts:
        hypotheses = {
            view: (
                PositionBootstrap(
                    tuple(value["satellite_indices"]), np.asarray(value["vector"]), ()
                ),
                case["prepared"][view].observations,
            )
            for view, value in receipt["hypotheses"].items()
        }
        ordered = sorted(
            donors,
            key=lambda donor: float(np.sum((np.asarray(donor[0]) - receipt["point_km"]) ** 2)),
        )
        fallback = {}
        for _, values in ordered:
            for index, value in values.items():
                fallback.setdefault(index, float(value))
        for view, prepared in case["prepared"].items():
            model = objective(prepared, bank, case["prior"], case["nodes"])
            seeds[view].append(
                shared_bootstrap_seed(model, indices, hypotheses, fallback_timings=fallback)
            )
    immutable(
        directory / "candidate-pool.json",
        {
            "candidate_full_indices": indices,
            "candidate_numbers": bank.numbers.tolist(),
            "original_candidate_numbers": case["bank"].numbers.tolist(),
            "proposals": proposals,
            "reference_usage": "none",
        },
    )
    for view, values in seeds.items():
        immutable(directory / "seeds" / f"{view}.json", values)
    return bank, seeds, indices
