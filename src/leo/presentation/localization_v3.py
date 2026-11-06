"""Plot evidence directly from an owned selected likelihood, without replay IO.

Evaluation coordinates belong only to the existing PNG renderer. They are not
accepted by prediction preparation or the conditional diagnostic grid.
"""

import hashlib
import json
import time

import numpy as np

from leo.analysis.localization_v3.reassociation_context import family_score, objective
from leo.analysis.position_grid import sample_position_grid
from leo.presentation.localization_v3_orbits import calibrated_lanes


def owner_digest(value):
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def prepare_packet(
    context,
    owners,
    expected,
    observations,
    tracks,
    *,
    selected_model,
    position_path,
    include_grid=True,
    grid_seconds=300.0,
    clock=time.monotonic,
    map_grid_batches=None,
):
    """Preserve every published point's prediction and the original plot order.

    The context carries the selected fit from numerical recovery. No optimizer,
    archive read, prior completion or legacy-result reconstruction runs here.
    """
    native = {o["observation_id"]: o for o in observations}
    if len(native) != len(observations):
        raise ValueError("Duplicate native observation")
    all_rows, summaries, differences, lanes = {}, {}, {}, None
    for arm, (problem, x) in context["problems"].items():
        saved = expected[arm]
        coordinates = problem.scan.search_region.latlon(x)
        if not np.allclose(coordinates, saved["endpoint_latlon"], rtol=0, atol=1e-9):
            raise ValueError("Published position changed during figure preparation")
        calculation = problem.calculate(x)
        score = objective(problem, context, x)
        delta = score - saved.get("negative_twice_elbo", saved.get("objective"))
        if not np.isfinite(delta) or abs(delta) > 1e-4:
            raise ValueError(f"{arm} objective mismatch {delta}")
        differences[arm] = float(delta)
        rows = {}

        def add(ids, residual, norad, component, role, arm=arm, rows=rows):
            for oid, value in zip(ids, residual, strict=True):
                if owners[arm].get(oid) != int(norad):
                    continue
                observation = native[oid]
                rows[oid] = dict(
                    observation_id=oid,
                    receiver=observation["receiver"],
                    channel=observation["channel"],
                    time_s=observation["time_s"],
                    measured_cfo_hz=observation["measured_cfo_hz"],
                    norad=int(norad),
                    residual_hz=float(value),
                    prediction_hz=float(observation["measured_cfo_hz"] - value),
                    component=component,
                    role=role,
                )

        for row, index, sl in zip(problem.rows, problem.members, problem.slices, strict=True):
            track = problem.scan.tracks[index]
            add(
                track["observation_ids"],
                calculation["conditional_residual_hz"][sl],
                row["candidate_norad"],
                track["key"],
                "conditional",
            )
        for entry, sl in zip(
            context["entries"], getattr(problem, "linear_slices", []), strict=True
        ):
            track = problem.scan.tracks[entry["track_index"]]
            add(
                track["observation_ids"],
                calculation["linear_raw_prediction_residual_hz"][sl],
                entry["norad"],
                track["key"],
                "predictive",
            )
        families = context["families"]
        details = (
            [
                families[0].evaluate(
                    problem,
                    x,
                    context["powers"],
                    context["entries"],
                    details=True,
                    refine_phase=False,
                )
            ]
            if len(families) == 1
            else family_score(families, context, problem, x, details=True)[1]
            if families
            else []
        )
        for family, detail in zip(families, details, strict=True):
            for entry, diagnostic in zip(family.entries, detail["diagnostics"], strict=True):
                add(
                    entry["observation_ids"],
                    diagnostic["raw_residual_hz"],
                    entry["norad"],
                    entry["component"],
                    "phase_mixture_MAP",
                )
        if arm == "fitted_c":
            lanes = calibrated_lanes(
                problem, x, calculation, observations, owners[arm], families, details
            )
        if set(rows) != set(owners[arm]):
            missing = len(set(owners[arm]) - set(rows))
            raise ValueError(f"{arm}: predictions missing for {missing} published points")
        all_rows[arm] = list(rows.values())
        summaries[arm] = dict(
            endpoint_latlon=list(map(float, saved["endpoint_latlon"])),
            associated_points=len(owners[arm]),
            associated_percent=100 * len(owners[arm]) / len(native),
            tracks=len({r["component"] for r in rows.values()}),
            satellites=len(set(owners[arm].values())),
            residual_rms_hz=float(np.sqrt(np.mean([r["residual_hz"] ** 2 for r in rows.values()]))),
            owner_sha256=owner_digest(owners[arm]),
        )
    packet = dict(
        observations=observations,
        tracks=tracks,
        rows=all_rows,
        orbit_lanes=lanes,
        arms=summaries,
        objective_replay=differences,
        selected_model=selected_model,
        position_path=position_path,
    )
    if include_grid:
        grid = sample_position_grid(
            lambda arm, x: objective(context["problems"][arm][0], context, np.asarray(x)),
            {arm: list(x) for arm, (_, x) in context["problems"].items()},
            maximum_seconds=grid_seconds,
            clock=clock,
            map_batches=map_grid_batches,
        )
        grid["endpoint_latlon"] = {a: r["endpoint_latlon"] for a, r in summaries.items()}
        region = context["scan"].search_region
        grid["region_center"] = list(region.center)
        grid["endpoint_objective_replay"] = differences
        for point in grid["points"]:
            point["latlon"] = list(map(float, region.latlon((point["east_km"], point["north_km"]))))
        packet["position_grid"] = grid
    return packet
