"""Untimed factor, score and fallback checks on two authenticated saved likelihoods."""

from collections import Counter
import argparse
from contextlib import nullcontext
import ctypes as ct
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from .profiled_grid_export import build, export_source, handoff, profiled_exports


RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
ORIGINAL = RELEASE/"assets/native/native_bound.so"
POSTERIOR = Path("/opt/leo-algo08/algo08v3/payload/posterior-grid-handoff.so")
ROOT = Path("/tmp/leo-algo08v2-2x-bench/dense-likelihood-capture-south")
PINS = {
    "capture.json": "b83280f71374946ff21f489479fa03cd1a53331203c98438e3ed7b421aaa3b19",
    "sample-00.npz": "33338a344cde41bf2444a22dc34a9ca95b1ea91c7de20dd2c402684008b9b04e",
    "sample-02.npz": "da78a84466a178ae50570257f8fa458394361d962ddd23b37200ace98ff49333",
    ORIGINAL.name: "c649042b2a5ddf7890177d84b302a19edcf7a662aea16c18cb177317ccba818b",
    POSTERIOR.name: "5a6e5627844a07a3bf2291b248520949f8b10e41d0421b6d6dc0da2b19d430b5",
}


def checked(path):
    body = path.read_bytes()
    if sha256(body).hexdigest() != PINS[path.name]:
        raise ValueError(f"Changed saved operand or runtime: {path}")
    return body


def invoke(stock, bound, args, options, clocks=None):
    cap = handoff.Capture(args[1].shape[1])

    def capture_call(*original):
        if clocks is None:
            return cap.run(bound, stock, original)
        started = process_time_ns()
        status = cap.run(bound, stock, original)
        clocks["capture_cpu_ns"] = process_time_ns()-started
        return status

    with patch.object(bound, "run", capture_call):
        if clocks is None:
            result = bound(*args, **options)
        else:
            cpu, wall = process_time_ns(), perf_counter_ns()
            result = bound(*args, **options)
            clocks.update(call_cpu_ns=process_time_ns()-cpu, call_wall_ns=perf_counter_ns()-wall)
    return result, cap


def check_factor(cap, result, u, sigma, groups, powers):
    _, groups = np.unique(groups, return_inverse=True)
    weights = (powers[groups]*result["noise_precision"][groups])/sigma**2
    gram = np.diag(result["coefficient_prior_precision"]) + u.T @ (u*weights[:, None])
    reconstructed = cap.lower @ cap.lower.T
    expect = gram[np.ix_(cap.order, cap.order)]
    np.testing.assert_allclose(reconstructed, expect, rtol=2e-10, atol=2e-9)
    return float(np.max(np.abs(reconstructed-expect)))


def operands(path, width):
    with np.load(BytesIO(checked(path)), allow_pickle=False) as record:
        args = tuple(record[k] for k in ("raw", "features", "sigma", "groups"))
        options = {k: record[k] for k in ("powers", "prior_groups", "prior_nu")}
    if args[1].shape != (4122, width):
        raise ValueError("Changed saved likelihood layout")
    return args, options


def check_case(stock, binary, binary_pin, args, options, expected_status, *, proof=False):
    bound = handoff.native_bound.NativeBound(ORIGINAL)
    handoff.bind_export(stock, bound)
    audit = Counter()
    try:
        baseline, old = invoke(stock, bound, args, options)
        old_valid = old.valid()
        stock_counts = bound.counts.copy()
        with profiled_exports(binary, binary_pin, audit, proof_stock=POSTERIOR if proof else None):
            proposed, new = invoke(stock, bound, args, options)
            new_valid = new.valid()
        new_counts = {key: value-stock_counts[key] for key, value in bound.counts.items()}
    finally:
        bound.clear()
    if stock_counts[expected_status] != 1 or new_counts[expected_status] != 1 or audit["attempted"] != 1:
        raise ValueError("Changed captured replay backend")
    delta_loss = abs(baseline["negative_twice_elbo"]-proposed["negative_twice_elbo"])
    delta_rf = float(np.max(np.abs(baseline["conditional_residual_hz"]-proposed["conditional_residual_hz"])))
    result = dict(native=expected_status, clocked=False, applied=dict(audit), rows=len(args[0]), width=args[1].shape[1],
                  updates=[int(r["precision_iterations"]) for r in (baseline, proposed)],
                  original_objective=float(baseline["negative_twice_elbo"]),
                  abs_curved_loss_change=float(delta_loss), max_residual_hz_change=delta_rf)
    if expected_status == "activated":
        if not old_valid or not new_valid or audit["profiled_completed"] != 1:
            raise ValueError("The saved successful likelihood did not export both checks")
        result["maximum_gram_delta"] = [check_factor(cap, r, *args[1:], options["powers"])
                                         for cap, r in ((old, baseline), (new, proposed))]
        # Diagnostic predictor using a fixed, unretuned slice of the saved design.
        raw, u, sigma, groups = args
        _, selected_groups = np.unique(groups[::53], return_inverse=True)
        scores = []
        for cap, fit in ((old, baseline), (new, proposed)):
            score = handoff.predictive_factor(raw[::53]-u[::53]@fit["coefficient"], u[::53], sigma[::53],
                                              selected_groups, cap, len(options["powers"]))
            scores.append(float(score["objective"]))
        result["fixed_slice_predictive_loss_delta"] = abs(scores[0]-scores[1])
        result["near_equivalence_gate"] = delta_loss <= 1e-5 and delta_rf <= .02 and abs(scores[0]-scores[1]) <= .01
    else:
        key = "certified_stock_refusal" if proof else "stock_replay"
        result["exact_fallback"] = (audit[key] == 1 and not old_valid and not new_valid
                                    and old.exported.value == new.exported.value == 0
                                    and all(stock_counts[k] == new_counts[k] for k in stock_counts
                                            if k not in {"cache_hits", "cache_misses"})
                                    and all(np.asarray(proposed[k]).tobytes() == np.asarray(v).tobytes()
                                            for k, v in baseline.items()))
        if not result["exact_fallback"]:
            raise ValueError("The refused profiled export changed ordinary fallback")
    return result


def checks():
    capture = json.loads(checked(ROOT/"capture.json"))
    checked(ORIGINAL)
    checked(POSTERIOR)
    stock = ct.CDLL(str(POSTERIOR)).nb_run_posterior
    inputs = (("c0", "sample-00.npz", 103, "activated"),
              ("fitted_c", "sample-02.npz", 104, "fallback_ill_conditioned"))
    arms = {}
    for arm, name, width, status in inputs:
        if capture["samples"][name]["caller"] != "history_position":
            raise ValueError("Expected the authorized saved selected likelihood")
        arms[arm] = (*operands(ROOT/name, width), status)
    return stock, arms


def run(*, proof=False):
    stock, cases = checks()
    with TemporaryDirectory(prefix="stock-profiled-grid-proof-") as temp:
        binary = Path(temp)/"profiled.so"
        pin = build(binary, prefix_proof=proof)
        arms = {arm: check_case(stock, binary, pin, *params, proof=proof) for arm, params in cases.items()}
        return dict(inputs=PINS, native_sha256=pin, prefix_proof=proof, arms=arms, performance_measurements=0)


def condition_source(source, symbol):
    source = handoff.replace(source, f"int {symbol}(", """
static _Thread_local int refusal_pass, refusal_gate;
static _Thread_local double refusal_ratio;
void condition_trace(int *pass, int *gate, double *ratio) {
    *pass=refusal_pass; *gate=refusal_gate; *ratio=refusal_ratio;
}
""" + f"int {symbol}(")
    gates = (("private_block", "det<min_rcond*norm*norm){", "det/(norm*norm)"),
             ("schur", "rcond<min_rcond){", "rcond"),
             ("full_bound", "1./full_norm/inverse_norm<min_rcond)) {\n            ", "1./full_norm/inverse_norm"))
    for gate, (_, subject, ratio) in enumerate(gates, 1):
        code = subject + "code=NB_CONDITION;goto done;"
        source = handoff.replace(source, code, subject +
            f"refusal_pass=iteration; refusal_ratio={ratio}; refusal_gate={gate}; code=NB_CONDITION;goto done;")
    return source


def condition_trace(binary):
    trace = ct.CDLL(str(binary)).condition_trace
    trace.argtypes = [ct.POINTER(ct.c_int), ct.POINTER(ct.c_int), ct.POINTER(ct.c_double)]
    trace.restype = None
    iteration, gate, ratio = ct.c_int(), ct.c_int(), ct.c_double()
    trace(ct.byref(iteration), ct.byref(gate), ct.byref(ratio))
    return iteration.value, gate.value, ratio.value


def audit_conditioning():
    """Prove the matched failed condition guard without clocking a fit."""
    stock, cases = checks()
    args, options, _ = cases["fitted_c"]
    with TemporaryDirectory(prefix="profiled-grid-condition-proof-") as temp:
        out = Path(temp)
        ordinary = out/"posterior-grid-handoff.so"
        handoff.build(ordinary)
        stock_build_sha256 = sha256(ordinary.read_bytes()).hexdigest()
        source = condition_source(ordinary.with_suffix(".c").read_text(), "nb_run_posterior")
        ordinary_diag = out/"ordinary-condition.so"
        ordinary_pin = build(ordinary_diag, source=source)
        binary = out/"condition.so"
        changed_pin = build(binary, source=condition_source(export_source(), "nb_profiled_posterior"))
        traced_stock = ct.CDLL(str(ordinary_diag)).nb_run_posterior
        bound = handoff.native_bound.NativeBound(ORIGINAL)
        handoff.bind_export(traced_stock, bound)
        handoff.bind_export(stock, bound)
        counters = Counter()
        try:
            _, old = invoke(traced_stock, bound, args, options)
            before = condition_trace(ordinary_diag)
            with profiled_exports(binary, changed_pin, counters):
                _, new = invoke(stock, bound, args, options)
            after = condition_trace(binary)
            if (old.valid() or new.valid() or counters["stock_replay"] != 1
                    or bound.counts["fallback_ill_conditioned"] != 2 or before != after or before[:2] != (2, 3)):
                raise ValueError("Ordinary and proposed condition refusals differ")
            return dict(refusal_iteration=before[0], gate="full_bound", estimated_reciprocal_condition=before[2],
                        min_rcond=bound.min_rcond, uninstrumented_stock_build_sha256=stock_build_sha256,
                        ordinary_diagnostic_sha256=ordinary_pin, profiled_diagnostic_sha256=changed_pin,
                        stock_condition_identical=True, performance_measurements=0)
        finally:
            bound.clear()


def time_captures(binary, pin, lease_fd, admission_ns, *, proof):
    from .field_crossover_admission_watch import (
        CAMPAIGN, recent_deferral,
    )
    from time import time_ns
    import fcntl

    lock = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
    if (os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) != 15
            or not os.path.samestat(os.fstat(lease_fd), lock.stat())):
        raise ValueError("Require the admitted single-core idle-priority scope")
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
                     "NUMEXPR_NUM_THREADS"):
        if os.environ.get(variable) != "1":
            raise ValueError("Require one numerical thread")
    fcntl.flock(lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    began, clock_start = time_ns(), process_time_ns()
    event = recent_deferral(CAMPAIGN, admission_ns-1, began)
    if event is None or event["unix_ns"] != admission_ns or not 0 <= began-admission_ns <= 5_000_000_000:
        raise ValueError("Prior official storage deferral was not visible to the child")
    stock, cases = checks()
    bound = handoff.native_bound.NativeBound(ORIGINAL)
    handoff.bind_export(stock, bound)
    try:
        # Symmetric one-call untimed setup per saved operand to model the normal grid's warmed provider.
        for args, options, _ in cases.values():
            invoke(stock, bound, args, options)
        loaded = process_time_ns()
        timings = {arm: [] for arm in cases}
        order = ("stock", "profiled", "proof") if proof else ("stock", "profiled")
        for mode in (*order, *reversed(order)):
            audit = Counter()
            admitted = (nullcontext() if mode == "stock" else profiled_exports(
                binary, pin, audit, proof_stock=POSTERIOR if mode == "proof" else None,
            ))
            began_bind = process_time_ns()
            with admitted:
                binding = process_time_ns()-began_bind
                for arm, (args, options, status) in cases.items():
                    row = dict(mode=mode)
                    prior = bound.counts[status]
                    previous_audit = audit.copy()
                    result, factor = invoke(stock, bound, args, options, clocks=row)
                    if bound.counts[status] != prior+1 or factor.valid() != (status == "activated"):
                        raise ValueError("Timed callback left the verified export or refusal path")
                    row.update(updates=int(result["precision_iterations"]), cache_hits=bound.counts["cache_hits"],
                               activity=dict(audit-previous_audit), context_entry_cpu_ns=binding)
                    timings[arm].append(row)
    finally:
        bound.clear()
    if proof and any(row["activity"] != {"attempted": 1, "certified_stock_refusal": 1}
                     for row in timings["fitted_c"] if row["mode"] == "proof"):
        raise ValueError("Timed proof did not match the current refusal")
    return dict(times=timings, original_inputs=PINS, native_sha256=pin, event=event,
                numerical_setup_cpu_ns=loaded-clock_start, checker_cpu_ns=process_time_ns()-clock_start,
                invocation="saved predictive capture, anticipated cache hits, no grid evaluation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timing-library", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--lease-fd", type=int)
    parser.add_argument("--admission-ns", type=int)
    parser.add_argument("--audit-conditioning", action="store_true")
    parser.add_argument("--proof-prefix", action="store_true")
    cli = parser.parse_args()
    if cli.timing_library:
        report = time_captures(cli.timing_library, cli.sha256, cli.lease_fd, cli.admission_ns, proof=cli.proof_prefix)
    elif cli.audit_conditioning:
        report = audit_conditioning()
    else:
        report = run(proof=cli.proof_prefix)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
