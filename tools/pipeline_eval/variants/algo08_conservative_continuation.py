"""Seed a matched conservative fitted-c fit from the physical fixed-zero fit."""

from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import conservative_recovery, retained_position
from leo.contracts.digests import canonical_digest


FIT_POSITION_SHA256 = "5e0a1ebde12b64a213b7f7f4a9a1035ff5f2f988f6016d47e60877b9d45e8d13"
PHASE_TOLERANCE_S = 0.01


def seedable_position():
    """Change only the initial geometric reference in the pinned five-round fit."""
    original = retained_position.fit_position
    source = getsource(original)
    if sha256(source.encode()).hexdigest() != FIT_POSITION_SHA256:
        raise ValueError("Retained fit source differs from the reviewed implementation")
    source = source.replace("rounds=5, iterations=48\n", "rounds=5, iterations=48, *, initial_phase\n", 1)
    source = source.replace("phase = np.zeros(len(labels))", "phase = np.asarray(initial_phase, float).copy()", 1)
    function = {}
    exec(compile(source, "<conservative calibration continuation>", "exec"), original.__globals__, function)
    return function["fit_position"]


def stable(record):
    return (record["fit"]["stopped"] == "small_bounded_step"
            and record["max_last_phase_change_s"] <= PHASE_TOLERANCE_S)


def physical_seed(problem, record):
    if not stable(record):
        return None
    point = np.asarray(record["endpoint_east_north_km"], float)
    phase = np.asarray(record["state"]["phases"], float)[problem.labels]
    if (point.shape != (2,) or phase.shape != (len(problem.labels),) or not phase.size
            or not np.isfinite(point).all() or not np.isfinite(phase).all()
            or np.any(point < problem.lower) or np.any(point > problem.upper)):
        return None
    return point.copy(), np.clip(phase, -15, 15)


def replay_endpoint(scan, node, keep, arm, record):
    """Independently rebuild the endpoint with its own arm's exact likelihood."""
    point = record["endpoint_east_north_km"]
    if (not np.array_equal(point, record["fit"]["parameters"])
            or not np.allclose(scan.search_region.latlon(point), record["endpoint_latlon"], atol=1e-9, rtol=0)):
        raise ValueError("Conservative endpoint differs from its fit and search region")
    fresh = retained_position.PositionNormal(scan, node, scan.radio_sigma_hz, arm == "fitted_c",
                                             reference=record["phase_reference"], keep=keep)
    fresh.phase_sigma = record["phase_widths_s"].copy()
    calculated = fresh.calculate(point)
    residual = np.r_[calculated["residual"], np.maximum(0, -calculated["elevation"][keep]) / 2]
    delta = float(calculated["negative_twice_elbo"] - record["fit"]["negative_twice_elbo"])
    score_delta = float(residual @ residual - record["score"])
    if any(not np.isfinite(value) or abs(value) > 1e-5 for value in (delta, score_delta)):
        raise ValueError("Conservative independent endpoint objective failed replay")
    return dict(negative_twice_elbo=float(calculated["negative_twice_elbo"]),
                replay_delta=delta, residual_score_delta=score_delta)


def pair_calls(stock, seeded, calls, *, audit=replay_endpoint):
    donor = None

    def accept(scan, node, keep, arm, *, rounds=5, iterations=48):
        nonlocal donor
        start = process_time_ns()
        previous, donor = donor, None
        mode, reason = "stock", None
        if seeded is not None and arm == "fitted_c" and previous is not None:
            old_scan, old_node, old_keep, old_budget, seed = previous
            if (scan is old_scan and node is old_node and np.array_equal(keep, old_keep)
                    and (rounds, iterations) == old_budget):
                point, phase = seed
                try:
                    problem, record = seeded(scan, node, keep, [], arm, "native", start=point,
                                             initial_phase=phase, rounds=rounds, iterations=iterations)
                    if stable(record):
                        mode = "continued"
                    else:
                        reason = "seeded fit did not settle"
                except (ValueError, ArithmeticError, np.linalg.LinAlgError) as error:
                    reason = str(error)
        if mode == "stock":
            problem, record = stock(scan, node, keep, arm, rounds=rounds, iterations=iterations)
        if seeded is not None and arm == "c0":
            seed = physical_seed(problem, record)
            if seed is not None:
                donor = scan, node, keep.copy(), (rounds, iterations), seed
        fit_cpu_ns = process_time_ns() - start
        point = record["endpoint_east_north_km"]
        diagnostics = audit(scan, node, keep, arm, record)
        science = [(row["component"], int(row["candidate_index"]), int(alias))
                   for row, alias in zip(problem.rows, problem.alias, strict=True)]
        calls.append(dict(
            arm=arm, mode=mode, fallback=reason, fit_cpu_ns=fit_cpu_ns,
            audit_cpu_ns=process_time_ns() - start - fit_cpu_ns,
            active_points=int(keep.sum()), active_fit_sha256=canonical_digest(
                [science, sha256(keep.tobytes()).hexdigest()]),
            initial_point_km=record["history"][0]["fit"]["history"][0]["parameters"].tolist(),
            initial_phase_s=record["history"][0]["phase_reference"].tolist(),
            final_phase_s=record["phase_reference"].tolist(),
            evaluations=[r["fit"]["evaluations"] for r in record["history"]],
            endpoint_km=point.tolist(), last_phase_change_s=record["max_last_phase_change_s"],
            stopped=record["fit"]["stopped"], rms_hz=record["frequency_rms_hz"], **diagnostics,
        ))
        return problem, record

    return accept


@contextmanager
def measured_continuation(*, enabled, audit=replay_endpoint):
    gate, fit = conservative_recovery.fit_and_gate, conservative_recovery.causal_fit
    seeded = seedable_position() if enabled else None
    measured = []

    def fit_and_gate(scan, node, keep, stage, *args, **kwargs):
        if kwargs.get("map_arms") is not None:
            return gate(scan, node, keep, stage, *args, **kwargs)
        calls = []
        with patch.object(conservative_recovery, "causal_fit", pair_calls(fit, seeded, calls, audit=audit)):
            result = gate(scan, node, keep, stage, *args, **kwargs)
        measured.append(dict(stage=stage, history=result[3], stable=result[4], calls=calls))
        return result

    with patch.object(conservative_recovery, "fit_and_gate", fit_and_gate):
        yield measured
