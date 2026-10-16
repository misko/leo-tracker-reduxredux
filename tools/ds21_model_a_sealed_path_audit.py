"""Read-only post-seal A path audit; training selection is never changed."""

import argparse
import json
from pathlib import Path

import ds21_model_a_pipeline_cached_v2 as cached
import numpy as np

from leo.analysis.regional_position_score import coordinates, zero_sum_basis
from leo.contracts.regional_position import RegionalPrior

original = cached.original


def bound_nodes(receipt, key):
    if original.binding(receipt["path"]) != receipt:
        raise ValueError("Bound orbit array bytes changed")
    with np.load(receipt["path"], allow_pickle=False) as data:
        return data[key].copy()


def validated_case(directory):
    directory = Path(directory).resolve()
    protocol = original.read(directory / "protocol.json")
    terminal = original.read(directory / "terminal.json")
    if protocol["policy"]["schema"] == cached.POLICY["schema"]:
        frozen = cached.read_control(directory)
        science = frozen["scientific"]
        outcomes = {u: cached.validate_unit(directory, u, frozen) for u in cached.UNITS}
        if terminal["protocol"] != original.binding(directory / "protocol.json") or terminal[
            "units"
        ] != {u: original.binding(directory / "units" / u / "terminal.json") for u in outcomes}:
            raise ValueError("Full cached matrix terminal binding differs")
        cache = cached.prepared_cache.validate(directory, frozen)
        nodes = bound_nodes(cache["arrays"], "bank_nodes_s")
    elif protocol["policy"]["schema"] == cached.authority.coverage.POLICY["schema"]:
        science, parent = cached.authority.coverage.read_control(directory)
        outcomes = {
            u: cached.authority.coverage.sealed_unit(directory, u, science) for u in cached.UNITS
        }
        if (
            terminal["protocol_sha256"] != original.binding(directory / "protocol.json")["sha256"]
            or terminal["outcomes"] != outcomes
            or terminal["terminals"]
            != {u: original.binding(directory / "units" / u / "terminal.json") for u in outcomes}
        ):
            raise ValueError("Full original coverage matrix terminal differs")
        coverage = original.read(Path(parent["stages"]["coverage-discovery"]) / "protocol.json")
        nodes = bound_nodes(coverage["full_bank"], "nodes_s")
    else:
        raise ValueError("Explicit qualified cached-v2 or original coverage-v1 provider required")
    selections = {
        "A-all": original.select(
            [
                o["selection"]
                for u, o in outcomes.items()
                if u.startswith("A-") and o["selection"] is not None
            ]
        ),
        **{u: o["selection"] for u, o in outcomes.items() if not u.startswith("A-")},
    }
    if (
        terminal["selections"] != selections
        or terminal["label"] != science["label"]
        or terminal["reference_usage"] != "none"
        or terminal["held_usage"] != "none"
    ):
        raise ValueError("Full twelve-unit own training selector differs")
    case = original.read_bound(science["case_protocol"])
    source = original.read_bound(case["source_protocol"])
    if source["member"]["role"] != "development":
        raise ValueError("Development-only post-seal path audit")
    return science, outcomes, nodes, selections["A-all"]


def stage(row, science, nodes, expected):
    fit = row["fit"]
    if "vector" not in fit:
        return dict(
            stationary=row["stationary"], error_type=fit.get("error_type"), reason=fit.get("reason")
        )
    vector = np.asarray(fit["vector"], float)
    point, center = vector[:2], np.asarray(row["local_center"], float)
    view = "all" if row["call"] == "final" else row["call"]
    frame = science["inputs"]["training_frames"][view]
    minimum = max(-20.0, float(nodes[0] - frame["minimum_time_s"]))
    maximum = min(20.0, float(nodes[-1] - frame["maximum_time_s"]))
    timings = vector[7] + zero_sum_basis(len(science["inputs"]["candidate_numbers"])) @ vector[8:]
    timing_slack = float(min(np.min(timings - minimum), np.min(maximum - timings)))
    prior = RegionalPrior(**science["inputs"]["prior"])
    global_slack = float(prior.radius_km**2 - point @ point)
    radius = row["options"].get("local_radius_km")
    local_slack = None if radius is None else float(radius**2 - (point - center) @ (point - center))
    calculated = min(timing_slack, global_slack, np.inf if local_slack is None else local_slack)
    if not np.isclose(calculated, fit["physical_constraints_minimum"], rtol=0, atol=1e-6):
        raise ValueError("Saved physical-boundary minimum disagrees with original domain")
    nuisance = np.asarray(fit["nuisance"])
    from ds21_evaluate import distance_km

    return dict(
        stationary=row["stationary"],
        point_km=point.tolist(),
        error_km=distance_km(coordinates(prior, point), expected),
        seed_point_km=row["seed"]["vector"][:2],
        movement_from_seed_km=float(np.linalg.norm(point - row["seed"]["vector"][:2])),
        distance_from_proposal_km=float(np.linalg.norm(point - center)),
        local_radius_km=radius,
        local_disk_slack_km2=local_slack,
        local_disk_active=local_slack is not None and local_slack <= 1e-6,
        regional_disk_slack_km2=global_slack,
        regional_disk_active=global_slack <= 1e-6,
        satellite_timing_minimum_slack_s=timing_slack,
        satellite_timing_active=timing_slack <= 1e-6,
        common_timing_box_active=abs(vector[7]) >= 10 - 1e-7,
        slope_boxes_active=[abs(vector[i]) >= 60 - 1e-7 for i in (3, 5)],
        fitted_c_box_active=abs(vector[6]) >= 5000 - 1e-7,
        nuisance_clock_box_active=(
            row["call"] != "high" and bool(np.any(abs(nuisance) >= 2000 - 1e-7))
        ),
        reported_boundary=fit["boundary"],
        reported_physical_constraints_minimum=fit["physical_constraints_minimum"],
        satellite_timings_s=timings.tolist(),
        fitted_c=float(vector[6]),
        objective=fit["objective"],
        likelihood_nll=fit["likelihood_nll"],
        posterior_rms_hz=fit["posterior_rms_hz"],
        stationarity=fit["stationarity"],
        solver_success=fit["solver_success"],
        group_offsets_hz=fit["group_offsets_hz"],
    )


def audit_paths(science, outcomes, nodes, selected, expected):
    eligible = sorted(
        [
            o["selection"]
            for u, o in outcomes.items()
            if u.startswith("A-") and o["selection"] is not None
        ],
        key=lambda r: (r["fit"]["objective"], r["start"]),
    )
    ranks = {row["start"]: i + 1 for i, row in enumerate(eligible)}
    paths = []
    for index in range(6):
        outcome = outcomes[f"A-{index}"]
        stages = {
            key: stage(row, science, nodes, expected) for key, row in outcome["calls"].items()
        }
        low, high, final = (stages.get(k) for k in ("low", "high", "final"))
        row = dict(
            start=index,
            proposal=science["inputs"]["proposals"][index],
            selected_by_training=selected is not None and selected["start"] == index,
            training_final_rank=ranks.get(index),
            stages=stages,
            excluded_stages=[k for k, v in stages.items() if not v["stationary"]],
            unattempted_stages=[k for k in ("low", "high", "final") if k not in stages],
        )
        if low and high and "point_km" in low and "point_km" in high:
            row["low_to_high_geographic_movement_km"] = float(
                np.linalg.norm(np.asarray(low["point_km"]) - high["point_km"])
            )
            delta = np.asarray(high["satellite_timings_s"]) - low["satellite_timings_s"]
            row["low_to_high_satellite_timing_rms_change_s"] = float(np.sqrt(np.mean(delta**2)))
        if low and final and "point_km" in low and "point_km" in final:
            row["low_to_final_geographic_movement_km"] = float(
                np.linalg.norm(np.asarray(low["point_km"]) - final["point_km"])
            )
            row["postseal_low_to_final_error_change_km"] = final["error_km"] - low["error_km"]
        paths.append(row)
    return paths


def audit(directory):
    directory = Path(directory).resolve()
    science, outcomes, nodes, selected = validated_case(directory)
    # Reference access is strictly after genuine complete matrix validation.
    from ds21_evaluate import reference

    paths = audit_paths(science, outcomes, nodes, selected, reference())
    return dict(
        schema="ds21-sealed-A-path-audit-v1",
        label=science["label"],
        scientific_schema=science["policy"]["schema"],
        protocol=original.binding(directory / "protocol.json"),
        terminal=original.binding(directory / "terminal.json"),
        paths=paths,
        selected_start=None if selected is None else selected["start"],
        selection="Unchanged minimum stationary own training final objective",
        reference_usage="Audit only after complete twelve-unit seal; never a selector",
        optimizer_calls=0,
        objective_calls=0,
        predictor_calls=0,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(cached.transport.native_json(audit(args.directory)), allow_nan=False))


if __name__ == "__main__":
    main()
