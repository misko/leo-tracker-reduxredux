"""Prepared full-census ambiguity audit: evaluate saved states, never optimize."""

import argparse
import hashlib
import json
import os
import runpy
import time
import types
from pathlib import Path

import numpy as np
from persistence import evaluate as persistence
from segments import prepare_segments

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUDIT = runpy.run_path(str(HERE.parent / "2026_10_09_position_error_iter87/audit.py"))
from leo.analysis.hard60_score import predict_orbits  # noqa: E402

ARMS = ("fitted-c", "zero-c")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def reconstruct(binding, archive):
    """Use immutable reconstruction once, retaining its prepared metadata."""
    original = AUDIT["reconstruct"]
    captured = []

    def load(bound):
        result = AUDIT["load"](bound)
        captured.append(result[0])
        return result

    # Copy the function namespace, leaving immutable87 and its global loader untouched.
    function = types.FunctionType(
        original.__code__,
        dict(original.__globals__, load=load),
        original.__name__,
        original.__defaults__,
        original.__closure__,
    )
    model = function(binding, archive)
    assert len(captured) == 1
    return model, captured[0].prepared.bootstrap_tracks


def predictions(model, vector, clock):
    relative = model.basis @ vector[8:]
    prediction, visible, _, _ = predict_orbits(
        model.bank, model.observations, model.prior, vector[:2], vector[7] + relative
    )
    prediction += (model.design @ vector[2:7] + model.baseline + model.clock_design @ clock)[
        :, None
    ]
    offsets, slopes = model.physical_corrections(clock)
    prediction += offsets[None, :] + model.delta_time * (100 * slopes)[None, :]
    return prediction, visible


def distribution(values):
    x = np.asarray(values)
    if not len(x):
        return None
    return dict(
        n=len(x),
        mean=float(x.mean()),
        median=float(np.median(x)),
        p95=float(np.percentile(x, 95)),
        maximum=float(x.max()),
    )


def ambiguity(terms, layout, numbers):
    posterior = np.column_stack([terms.clutter_probability, terms.responsibilities])
    np.testing.assert_allclose(posterior.sum(axis=1), 1, atol=1e-12, rtol=0)
    top = np.sort(posterior, axis=1)[:, -2:]
    confidence = top[:, 1]
    log_odds = np.log(np.maximum(top[:, 1], np.finfo(float).tiny)) - np.log(
        np.maximum(top[:, 0], np.finfo(float).tiny)
    )
    entropy = -np.sum(posterior * np.log(np.maximum(posterior, np.finfo(float).tiny)), axis=1)
    identities = np.r_[0, numbers][posterior.argmax(axis=1)]
    eligible = np.zeros(len(posterior), bool)
    pairs = []
    for segment in layout["segments"]:
        if len(segment) > 1:
            eligible[list(segment)] = True
            pairs.extend(zip(segment[:-1], segment[1:], strict=True))
    switches = dict(
        links=len(pairs),
        changed=0,
        satellite_to_satellite=0,
        involving_clutter=0,
        confident_satellite_switches=0,
        weak_or_clutter_switches=0,
    )
    for left, right in pairs:
        if identities[left] == identities[right]:
            continue
        switches["changed"] += 1
        clutter = identities[left] == 0 or identities[right] == 0
        confident = not clutter and min(confidence[left], confidence[right]) >= 0.9
        switches["involving_clutter" if clutter else "satellite_to_satellite"] += 1
        switches["confident_satellite_switches" if confident else "weak_or_clutter_switches"] += 1
    populations = {}
    for name, mask in (
        ("all", np.ones(len(posterior), bool)),
        ("linked", eligible),
        ("independent", ~eligible),
    ):
        populations[name] = dict(
            rows=int(sum(mask)),
            entropy_nats=distribution(entropy[mask]),
            top_two_log_odds=distribution(log_odds[mask]),
            maximum_probability=distribution(confidence[mask]),
            clutter_probability=distribution(terms.clutter_probability[mask]),
            confidence_below_half=int(sum(confidence[mask] < 0.5)),
            confidence_half_to_nine_tenths=int(
                sum((confidence[mask] >= 0.5) & (confidence[mask] < 0.9))
            ),
            confidence_at_least_nine_tenths=int(sum(confidence[mask] >= 0.9)),
        )
    return dict(populations=populations, switches=switches)


def audit_arm(model, vector, clock, saved_objective, layout):
    value, _, _, terms = model.evaluate_joint(vector, clock)
    np.testing.assert_allclose(value, saved_objective, atol=1e-6, rtol=0)
    prediction, visible = predictions(model, vector, clock)
    order, inverse = layout["permutation"], layout["inverse_permutation"]
    independent = persistence(
        model.observations.measured_hz[order],
        prediction[order],
        visible[order],
        model.score,
        rho=0,
        reset=layout["reset"],
    )
    relative = model.basis @ vector[8:]
    prior = 0.5 * (vector[7] / model.score.common_sigma_s) ** 2
    prior += 0.5 * np.sum((relative / model.score.relative_sigma_s) ** 2)
    prior += 0.5 * clock @ model.precision @ clock
    np.testing.assert_allclose(independent["nll"] + prior, value, atol=1e-6, rtol=0)
    difference = independent["prediction_gradient"][inverse] - terms.prediction_gradient
    np.testing.assert_allclose(difference, 0, atol=1e-12, rtol=0)
    return dict(
        objective_stored=float(saved_objective),
        objective_reconstructed=float(value),
        objective_delta=float(value - saved_objective),
        rho0_whole_score_delta=float(independent["nll"] + prior - value),
        rho0_prediction_gradient_max_abs=float(np.max(abs(difference))),
        ambiguity=ambiguity(terms, layout, model.bank.numbers),
    )


def evaluate(binding, digest):
    member = binding["member"]
    destination = HERE / "results" / f"{member['inventory_label']}.json"
    if destination.exists():
        stored = AUDIT["read"](destination)
        assert stored["protocol_sha256"] == digest and stored["member"] == member
        return
    begun = time.monotonic()
    receipt = dict(
        member=member,
        protocol_sha256=digest,
        loader_kind=binding["loader_binding"]["kind"],
        source=binding["b7_source"],
    )
    try:
        archive = AUDIT["read"](ROOT / binding["b7_source"])
        assert archive["status"] == "complete" and archive["member"] == member
        model, tracks = reconstruct(binding, archive)
        layout = prepare_segments(tracks, model.observations)
        receipt["coverage"] = layout["counts"]
        receipt["arms"] = {}
        for arm in ARMS:
            row = archive["stages"]["B7"][arm]
            assert row["converged"] and row["stage"] == "B7"
            vector, clock = np.asarray(row["vector"]), np.asarray(row["clock_coefficients"])
            if arm == "zero-c":
                assert vector[6] == 0 and np.all(clock[-2:] == 0)
            receipt["arms"][arm] = audit_arm(model, vector, clock, row["objective"], layout)
        receipt["status"] = "complete"
    except Exception as error:
        receipt.update(status="failed", error=repr(error))
    receipt["elapsed_s"] = time.monotonic() - begun
    write(destination, receipt)
    print(member["inventory_label"], receipt["status"], flush=True)


def main(shard):
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        assert os.environ.get(variable) == "1"
    path = HERE / "protocol.json"
    plan = AUDIT["read"](path)
    assert plan["optimizer_calls"] == 0 and plan["rho"] == 0
    assert len(plan["members"]) == 148 and 0 <= shard < plan["shards"] == 2
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    for index, binding in enumerate(plan["members"]):
        if index % 2 == shard:
            evaluate(binding, digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, required=True)
    main(parser.parse_args().shard)
