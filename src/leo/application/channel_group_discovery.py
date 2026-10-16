"""Bounded cold spatial discovery from independent training channel views."""

import time
from dataclasses import asdict

import numpy as np

from leo.analysis.channel_group_calibration import GroupCalibrationObjective, fit_group_calibration
from leo.analysis.channel_group_seeds import shared_bootstrap_seed
from leo.analysis.hard60_joint_clock import JointClockObjective
from leo.analysis.hard60_score import Hard60Objective, predict_orbits
from leo.analysis.regional_position_bootstrap import bootstrap_position
from leo.analysis.regional_position_search import hierarchical_search
from leo.application.hard60_runner import HARD60_SCORE


class DiscoverySliceExpired(TimeoutError):
    """A durable point receipt can be resumed in a separately bounded slice."""


def discover_channel_groups(
    prepared,
    bank,
    prior,
    point_port,
    *,
    maximum_seconds=500.0,
    points=100,
    clock_nodes=None,
    levels_km=(100.0, 50.0, 25.0, 12.5),
    priority_view="all",
):
    """Evaluate all views at the same points with the same candidate union.

    ``point_port`` supplies get/put of immutable point receipts. Candidates,
    receiver corrections, and timings originate exclusively in the supplied
    training preparation. This stage has no reference or full-data donor input.
    Upstream discovery uses fitted c; later matched c arms remain conditional.
    """
    if "all" not in prepared or not set(prepared) <= {"all", "low", "high"}:
        raise ValueError("all plus available independent training halves required")
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1500:
        raise ValueError("bounded discovery slice required")
    if priority_view not in prepared:
        raise ValueError("Search priority needs an available training view")
    deadline = time.monotonic() + maximum_seconds
    receipts = {}

    def priority_score(receipt):
        fit = receipt["fits"].get(priority_view, {})
        return float(fit["objective"]) if fit.get("converged") else 1e100

    def evaluate(east, north):
        key = f"point:{east:g}:{north:g}"
        saved = point_port.get(key)
        if saved is not None:
            receipts[key] = saved
            return priority_score(saved)
        if time.monotonic() + 30 >= deadline:
            raise DiscoverySliceExpired(key)
        hypotheses, failures = {}, {}
        for view, inputs in prepared.items():
            try:
                proposal = bootstrap_position(
                    inputs.observations,
                    bank,
                    prior,
                    [east, north],
                    inputs.bootstrap_tracks,
                    maximum_seconds=5.0,
                    orbit_predictor=predict_orbits,
                )
                hypotheses[view] = (proposal, inputs.observations)
            except (ValueError, TimeoutError) as error:
                failures[view] = f"{type(error).__name__}: {error}"
        indices = tuple(
            sorted(
                {i for proposal, _ in hypotheses.values() for i in proposal.satellite_indices},
                key=lambda i: bank.numbers[i],
            )
        )
        fits = {}
        if indices:
            subset = bank.select(list(indices))
            for view, inputs in prepared.items():
                try:
                    base = Hard60Objective(inputs.observations, subset, prior, HARD60_SCORE)
                    if clock_nodes is not None:
                        base = JointClockObjective(
                            base, clock_nodes, np.zeros((2, len(clock_nodes))), 4
                        )
                    model = GroupCalibrationObjective(base, inputs.observations.channel >= 5)
                    seed = shared_bootstrap_seed(model, indices, hypotheses)
                    fits[view] = fit_group_calibration(
                        model,
                        seed["vector"],
                        seed["nuisance"],
                        fixed_position=True,
                        seconds=5.0,
                        iterations=200,
                    )
                    fits[view]["projection_rms_hz"] = seed["projection"]["rms_hz"]
                except (ValueError, TimeoutError) as error:
                    failures[view] = f"{type(error).__name__}: {error}"
        eligible = fits.get("all", {})
        receipt = dict(
            east_km=east,
            north_km=north,
            satellite_indices=indices,
            catalogue_numbers=[int(bank.numbers[i]) for i in indices],
            fits=fits,
            failures=failures,
            selection_score=float(eligible["objective"]) if eligible.get("converged") else 1e100,
        )
        point_port.put(key, receipt)
        receipts[key] = receipt
        return priority_score(receipt)

    search = hierarchical_search(
        evaluate,
        radius_km=prior.radius_km,
        levels_km=levels_km,
        budget_points=points,
        edge_priority="nearest",
    )
    # One best candidate from each independent score, then separated full-view
    # candidates if winners coincide. Every subsequent view uses these starts.
    ranked = []
    for view in ("low", "high", "all"):
        eligible = [row for row in receipts.values() if row["fits"].get(view, {}).get("converged")]
        if eligible:
            ranked.append(
                min(
                    eligible,
                    key=lambda row: (
                        row["fits"][view]["objective"],
                        row["east_km"],
                        row["north_km"],
                    ),
                )
            )
    ranked.extend(
        sorted(
            (row for row in receipts.values() if row["selection_score"] < 1e100),
            key=lambda row: (row["selection_score"], row["east_km"], row["north_km"]),
        )
    )
    selected = []
    for row in ranked:
        point = np.array([row["east_km"], row["north_km"]])
        if all(
            np.linalg.norm(point - np.array([other["east_km"], other["north_km"]])) >= 12.5
            for other in selected
        ):
            selected.append(row)
        if len(selected) == 3:
            break
    return dict(
        search=asdict(search),
        selected=selected,
        points=len(receipts),
        available=len(selected) == 3,
        scope="Training-only discovery; no held prediction or accuracy evaluation",
        priority_view=priority_view,
    )
