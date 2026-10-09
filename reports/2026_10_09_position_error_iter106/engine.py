"""Fixed frequency-width experiment; no reference-coordinate access or selection."""

import argparse
import copy
import hashlib
import json
import os
import runpy
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUDIT = runpy.run_path(str(HERE.parent / "2026_10_09_position_error_iter87/audit.py"))
from leo.analysis.hard60_bounded_fit import _Problem  # noqa: E402
from leo.analysis.hard60_dynamic_rf import fit  # noqa: E402

ARMS = ("fitted-c", "zero-c")
WIDTHS = (125, 100)


def serial(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [serial(v) for v in value]
    return value


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(serial(value), stream, indent=2, allow_nan=False)
        stream.write("\n")


def width_model(model, width):
    assert width in WIDTHS
    changed = copy.copy(model)
    changed.score = replace(model.score, sigma_hz=float(width))
    return changed


def check_archive(model, archived):
    checks = {}
    control = width_model(model, 125)
    for arm in ARMS:
        row = archived["stages"]["B7"][arm]
        assert row["converged"] and row["stage"] == "B7"
        vector, clock = np.asarray(row["vector"]), np.asarray(row["clock_coefficients"])
        if arm == "zero-c":
            assert vector[6] == 0 and np.all(clock[-2:] == 0)
        original = model.evaluate_joint(vector, clock)
        copied = control.evaluate_joint(vector, clock)
        for i in range(3):
            np.testing.assert_array_equal(original[i], copied[i])
        np.testing.assert_allclose(copied[0], row["objective"], atol=1e-6, rtol=0)
        checks[arm] = dict(
            stored=row["objective"],
            reconstructed=float(copied[0]),
            delta=float(copied[0] - row["objective"]),
        )
    return checks


def qualify(model, seed, row, arm):
    """Repeat the production physical and clock KKT audit independently."""
    vector = np.asarray(row["vector"], float)
    clock = np.asarray(row["clock_coefficients"], float)
    assert np.isfinite(vector).all() and np.isfinite(clock).all()
    assert clock.shape == model.initial_clock.shape
    problem = _Problem(
        model, seed, rf_arm=arm, local_center=seed[:2], local_radius_km=25, slope_half_width_hz_s=60
    )
    value, gradient, clock_gradient, terms = model.evaluate_joint(vector, clock)
    assert np.isfinite(value) and np.isfinite(gradient).all() and np.isfinite(clock_gradient).all()
    np.testing.assert_allclose(value, row["objective"], atol=1e-6, rtol=0)
    low, high = np.full(len(clock), -2000.0), np.full(len(clock), 2000.0)
    locked = arm == "zero-c" or model.fixed_rf_drift
    low[-2:], high[-2:] = (0.0, 0.0) if locked else (-1000.0, 1000.0)
    if arm == "zero-c":
        assert vector[6] == 0 and np.all(clock[-2:] == 0)
    g = 50 * clock_gradient.copy()
    if locked:
        g[-2:] = 0
    g[(clock <= low + 1e-7) & (g >= 0)] = 0
    g[(clock >= high - 1e-7) & (g <= 0)] = 0
    kkt = max(problem.stationarity(vector, gradient), float(np.max(abs(g))))
    feasible = (
        problem.feasible(vector) and np.all(clock >= low - 1e-7) and np.all(clock <= high + 1e-7)
    )
    relative = model.basis @ vector[8:]
    timing = 0.5 * (vector[7] / model.score.common_sigma_s) ** 2
    timing += 0.5 * np.sum((relative / model.score.relative_sigma_s) ** 2)
    nuisance = 0.5 * clock @ model.precision @ clock
    np.testing.assert_allclose(value, terms.nll + timing + nuisance, atol=1e-6, rtol=0)
    indices = terms.responsibilities.argmax(axis=1)
    residual = terms.residual_hz[np.arange(len(indices)), indices]
    probability = terms.responsibilities[np.arange(len(indices)), indices]
    return dict(
        row,
        converged=bool(feasible and kkt <= 0.001),
        reported_converged=row["converged"],
        independent_stationarity=kkt,
        independently_feasible=bool(feasible),
        score_components=dict(
            frequency_nll=terms.nll, timing_prior=timing, nuisance_prior=nuisance, total=value
        ),
        frequency_diagnostics=dict(
            maximum_assignment_unweighted_rms_hz=float(np.sqrt(np.mean(residual**2))),
            maximum_assignment_policy="all rows, even when classified as clutter",
            selected_residual_hz=residual,
            maximum_responsibility=probability,
            assigned_satellite=np.where(probability > 0.5, model.bank.numbers[indices], 0),
            clutter_probability=terms.clutter_probability,
            clock_l2=float(np.linalg.norm(clock)),
        ),
    )


def run_attempt(model, seed, clock, arm, fitter=None):
    fitter = fit if fitter is None else fitter
    row = fitter(
        model,
        seed.copy(),
        arm=arm,
        clock_seed=clock.copy(),
        maximum_seconds=90,
        maximum_iterations=600,
    )
    return qualify(model, seed, row, arm)


def choose(attempt, fallback, source):
    if attempt["status"] == "complete" and attempt["fit"]["converged"]:
        return dict(fit=attempt["fit"], fallback=False, source="attempt")
    return dict(
        fit=fallback,
        fallback=True,
        source=source,
        reason=attempt.get("error", "independently unqualified"),
    )


def evaluate(binding, digest):
    member = binding["member"]
    label = member["inventory_label"]
    destination = HERE / "results" / f"{label}.json"
    if destination.exists():
        receipt = AUDIT["read"](destination)
        assert receipt["protocol_sha256"] == digest and receipt["member"] == member
        return
    began = time.monotonic()
    receipt = dict(
        member=member,
        protocol_sha256=digest,
        source_result=binding["b7_source"],
        loader_kind=binding["loader_binding"]["kind"],
    )
    try:
        archive = AUDIT["read"](ROOT / binding["b7_source"])
        assert archive["status"] == "complete" and archive["member"] == member
        model = AUDIT["reconstruct"](binding, archive)
        assert model.score.sigma_hz == 125
        receipt["objective_checks"] = check_archive(model, archive)
        fitted = archive["stages"]["B7"]["fitted-c"]
        seed, clock = np.asarray(fitted["vector"]), np.asarray(fitted["clock_coefficients"])
        receipt["shared_start"] = dict(vector=seed, clock_coefficients=clock)
        raw, operational = {}, {}
        for width in WIDTHS:
            name = str(width)
            raw[name], operational[name] = {}, {}
            current = width_model(model, width)
            for arm in ARMS:
                path = HERE / "attempts" / label / f"sigma{name}-{arm}.json"
                if path.exists():
                    attempt = AUDIT["read"](path)
                    assert attempt["protocol_sha256"] == digest
                    assert (
                        attempt["member"] == member
                        and attempt["width_hz"] == width
                        and attempt["arm"] == arm
                    )
                else:
                    attempt = dict(protocol_sha256=digest, member=member, width_hz=width, arm=arm)
                    try:
                        attempt.update(
                            status="complete", fit=run_attempt(current, seed, clock, arm)
                        )
                    except Exception as error:
                        attempt.update(status="failed", error=repr(error))
                    write(path, attempt)
                raw[name][arm] = attempt
                fallback = archive["stages"]["B7"][arm]
                source = "archived-B7"
                if width == 100 and operational["125"][arm]["fit"]["converged"]:
                    fallback = operational["125"][arm]["fit"]
                    source = (
                        "125-control" if not operational["125"][arm]["fallback"] else "archived-B7"
                    )
                operational[name][arm] = choose(attempt, fallback, source)
        receipt.update(status="complete", raw=raw, operational=operational)
    except Exception as error:
        receipt.update(status="failed", error=repr(error))
    receipt["elapsed_s"] = time.monotonic() - began
    write(destination, receipt)
    print(label, receipt["status"], flush=True)


def main(shard=None, label=None):
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        assert os.environ.get(variable) == "1", variable
    path = HERE / "protocol.json"
    plan = AUDIT["read"](path)
    assert plan["widths_hz"] == list(WIDTHS) and plan["maximum_seconds"] == 90
    assert plan["maximum_iterations"] == 600 and plan["stationarity_threshold"] == 0.001
    assert plan["shards"] == 2 and len(plan["members"]) == 148
    assert (shard is None) != (label is None)
    if shard is not None:
        assert 0 <= shard < 2
    else:
        assert label in plan["labels"]
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    for ordinal, binding in enumerate(plan["members"]):
        if binding["member"]["inventory_label"] == label or (
            shard is not None and ordinal % 2 == shard
        ):
            evaluate(binding, digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--shard", type=int)
    group.add_argument("--label")
    args = parser.parse_args()
    main(args.shard, args.label)
