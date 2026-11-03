"""One immutable prepared source per four-case family; no persistent cache."""

import argparse
import hashlib
import time
from dataclasses import replace

import numpy as np
import run_v2 as run
from numpy.testing import assert_array_equal


def arm_context(base, arm):
    vector, nuisance = base.vector.copy(), base.nuisance.copy()
    if arm == "zero-c":
        vector[6] = 0.0
    elif arm != "fitted-c":
        raise ValueError("Declared RF arm required")
    return replace(
        base,
        vector=vector,
        nuisance=nuisance,
        fixed_c=arm == "zero-c",
        deadline=time.monotonic() + 120,
    )


def fingerprint(context):
    arrays = [
        context.vector,
        context.nuisance,
        context.bank.numbers,
        context.bank.nodes_s,
        context.bank.position_km,
        context.bank.velocity_km_s,
        context.observations.times_s,
        context.observations.measured_hz,
        context.observations.rf_hz,
        context.observations.receiver,
        context.observations.channel,
        context.model.mask,
        context.model.original.design,
        context.model.original.clock_design,
        context.model.original.group_design,
        context.model.original.baseline,
    ]
    return hashlib.sha256(b"".join(np.ascontiguousarray(a).tobytes() for a in arrays)).hexdigest()


def one(
    context, method, callback, *, refitter=run.common.refit, free_fitter=run.fit_free, profile=None
):
    if method == "fixed":
        result = refitter(
            context,
            context.vector,
            context.nuisance,
            max_evaluations=1000,
            max_seconds=120,
            fixed_c=context.fixed_c,
        )
        target = context
    elif method == "joint":
        result, target, _ = free_fitter(
            context,
            max_evaluations=1000,
            max_seconds=120,
            reused_profile=profile,
            qualification_callback=callback,
        )
    else:
        raise ValueError("Declared policy required")
    if result["diagnostics"]["evaluations"] > 1000:
        raise ValueError("Inference objective/density budget exceeded")
    return result, target


def family(source):
    started = time.monotonic()
    run.verify()
    run.qualifications()
    run.verify_bindings(run.read(run.HERE / "execution_plan.json")["source_sha256"])
    prepared_at = time.monotonic()
    base, _ = run.prepare(source, "fitted-c")
    preparation_seconds = time.monotonic() - prepared_at
    original_fingerprint = fingerprint(base)
    records = []
    for arm in run.ARMS:
        qualification = run.read(run.HERE / f"qualification_{source}_{arm}.json")
        for method in run.METHODS:
            destination = run.HERE / f"fit_{source}_{arm}_{method}.json"
            if destination.exists():
                raise FileExistsError("No overwrite/retry of a completed case")
            context = arm_context(base, arm)
            assert_array_equal(context.vector, qualification["vector"])
            assert_array_equal(context.nuisance, qualification["nuisance"])
            assert_array_equal(context.bank.numbers, qualification["numbers"])

            def callback(value, _arm=arm):
                run.save(run.HERE / f"runtime_qualification_{source}_{_arm}.json", value)

            case_start = time.monotonic()
            result, target = one(
                context,
                method,
                callback,
                profile=run.read(run.HERE / f"profile_{source}_{arm}.json")
                if method == "joint"
                else None,
            )
            audit = run.common.endpoint_status(target, result["vector"], result["nuisance"])
            if fingerprint(base) != original_fingerprint:
                raise AssertionError("Prepared context mutated across cases")
            run.save(
                destination,
                dict(
                    result,
                    source_id=source,
                    arm=arm,
                    method=method,
                    audit=audit,
                    original_offsets_hz=run.free_context(context).model.original_offsets_hz,
                    qualification_sha256=run.digest(
                        run.HERE / f"qualification_{source}_{arm}.json"
                    ),
                    independent_audit_calls=1,
                    reference_or_window_evaluation=False,
                    source_preparation_reused=True,
                    context_fingerprint=original_fingerprint,
                ),
            )
            records.append(
                dict(
                    path=str(destination),
                    sha256=run.digest(destination),
                    active_case_seconds=time.monotonic() - case_start,
                )
            )
            print(source, arm, method, result["diagnostics"], "audit", audit, flush=True)
    run.verify()
    run.verify_bindings(run.read(run.HERE / "execution_plan.json")["source_sha256"])
    run.save(
        run.HERE / f"family_seal_{source}.json",
        dict(
            records=records,
            preparations=1,
            preparation_seconds=preparation_seconds,
            elapsed_seconds=time.monotonic() - started,
            context_unchanged=True,
            outer_seconds=540,
            outer_kill_seconds=545,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=run.SOURCES)
    family(parser.parse_args().source)
