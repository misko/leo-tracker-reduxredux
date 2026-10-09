"""Reconstruct all sealed B7 endpoints and audit residuals; never optimize."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARCHIVE = HERE.parent / "2026_10_09_position_error_iter85"
sys.path.insert(0, str(ARCHIVE))
from dependencies import (  # noqa: E402
    HARD60_SCORE,
    Hard60Objective,
    arm_selected,
    load,
    read,
    reduce_bank,
)

from leo.analysis.hard60_dynamic_rf import DynamicRFObjective  # noqa: E402
from leo.analysis.hard60_slope_prior import SlopePrior  # noqa: E402

sys.path.insert(0, str(HERE))
from residual_stats import summarize_residuals  # noqa: E402

ARMS = ("fitted-c", "zero-c")


def reconstruct(binding, archived):
    """Recreate the fitted-derived bank and centers using inference fields only."""
    case, baseline, _ = load(binding["loader_binding"])
    source = archived["region_sources"]["fitted-c"]
    document = baseline if source == "baseline" else read(ROOT / binding["regions"][source])
    for key in ("session_id", "input_manifest_sha256", "analysis_manifest_sha256"):
        assert document[key] == baseline[key], key
    selected = arm_selected(document, "fitted-c")
    calibration = document["diagnostics"]["calibrations"][selected["source_basin"]]
    correction = calibration["correction"]
    lookup = {int(number): i for i, number in enumerate(case.bank.numbers)}
    base = Hard60Objective(
        case.prepared.observations,
        case.bank.select([lookup[number] for number in selected["satellites"]]),
        case.prior,
        HARD60_SCORE,
        receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
    )
    joint = archived["raw"]["B3"]["fitted-c"]
    assert joint["converged"]
    subset, _, removed = reduce_bank(base, np.asarray(joint["vector"]), 5)
    assert removed == archived["reasons"]["removed_satellites"]
    chosen = archived["raw"]["B4"]["fitted-c"]
    assert chosen["converged"]
    wide = archived["raw"]["B4W"]["fitted-c"]
    if wide["converged"]:
        chosen = wide
    seed = np.asarray(chosen["vector"])
    clock = np.r_[chosen["clock_coefficients"], 0.0, 0.0]
    dynamic = archived["raw"]["B5"]["fitted-c"]
    if dynamic["converged"]:
        seed = np.asarray(dynamic["vector"])
        clock = np.asarray(dynamic["clock_coefficients"])
    nodes, knots = correction["nodes_s"], correction["knots_hz"]
    control = DynamicRFObjective(subset, nodes, knots, 50)
    terms = control.evaluate_joint(seed, clock)[3]
    mass = terms.responsibilities.sum(axis=0)
    centers = np.divide(
        terms.responsibilities.T @ subset.observations.times_s,
        mass,
        out=np.full(len(mass), subset.observations.time_center_s),
        where=mass > 1e-12,
    )
    return SlopePrior(subset, nodes, knots, centers, 0.5)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def evaluate(binding, digest):
    member = binding["member"]
    label = member["inventory_label"]
    destination = HERE / "results" / f"{label}.json"
    if destination.exists():
        assert read(destination)["protocol_sha256"] == digest
        return
    started = time.monotonic()
    receipt = dict(
        member=member,
        protocol_sha256=digest,
        source_result=binding["b7_source"],
        loader_kind=binding["loader_binding"]["kind"],
        objective_checks={},
    )
    try:
        archived = read(ROOT / binding["b7_source"])
        assert archived["status"] == "complete" and archived["member"] == member
        model = reconstruct(binding, archived)
        evaluated = {}
        for arm in ARMS:
            row = archived["stages"]["B7"][arm]
            assert row["stage"] == "B7" and row["converged"]
            vector = np.asarray(row["vector"])
            clock = np.asarray(row["clock_coefficients"])
            if arm == "zero-c":
                assert vector[6] == 0 and np.all(clock[-2:] == 0)
            objective, _, _, terms = model.evaluate_joint(vector, clock)
            receipt["objective_checks"][arm] = dict(
                stored=float(row["objective"]),
                reconstructed=float(objective),
                delta=float(objective - row["objective"]),
            )
            np.testing.assert_allclose(objective, row["objective"], atol=1e-6, rtol=0)
            evaluated[arm] = terms
        fitted = evaluated["fitted-c"]
        indices = fitted.responsibilities.argmax(axis=1)
        probability = fitted.responsibilities[np.arange(len(indices)), indices]
        numbers = np.where(probability > 0.5, model.bank.numbers[indices], 0)
        observations = model.observations
        arms = {}
        for arm, terms in evaluated.items():
            rows = [
                dict(
                    receiver=int(observations.receiver[i]),
                    satellite=int(numbers[i]),
                    channel=int(observations.channel[i]),
                    time_s=float(observations.times_s[i]),
                    residual_hz=float(terms.residual_hz[i, indices[i]]),
                    margin=float(observations.margin[i]),
                    assignment_probability=float(probability[i]),
                )
                for i in range(len(indices))
            ]
            arms[arm] = summarize_residuals(rows)
        receipt.update(
            status="complete",
            observation_count=len(indices),
            satellite_count=len(model.bank.numbers),
            assigned_count=int(np.sum(numbers > 0)),
            unassigned_count=int(np.sum(numbers == 0)),
            shared_assignment_policy="fitted-B7 maximum responsibility strictly above0.5",
            arms=arms,
        )
    except Exception as error:
        receipt.update(status="failed", error=repr(error))
    receipt["elapsed_s"] = time.monotonic() - started
    write(destination, receipt)
    print(label, receipt["status"], flush=True)


def main(shard):
    path = HERE / "protocol.json"
    plan = read(path)
    assert 0 <= shard < plan["shards"]
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    for ordinal, binding in enumerate(plan["members"]):
        if ordinal % plan["shards"] == shard:
            evaluate(binding, digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, required=True)
    main(parser.parse_args().shard)
