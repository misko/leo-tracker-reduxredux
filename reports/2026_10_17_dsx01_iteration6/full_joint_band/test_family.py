import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from numpy.testing import assert_array_equal

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("full_joint_family", HERE / "family.py")
family = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(family)


def context():
    return family.run.common.Context(
        "fixture",
        None,
        None,
        np.arange(12, dtype=float),
        np.array([1.0, 2.0, 3.0]),
        None,
        None,
        None,
        np.ones(2, bool),
        np.array([0.0, 1.0]),
        {},
    )


def test_shared_preparation_keeps_complete_seeds_independent_between_all_cases():
    base = context()
    fitted = family.arm_context(base, "fitted-c")
    zero = family.arm_context(base, "zero-c")
    expected = base.vector.copy()
    expected[6] = 0.0
    assert_array_equal(zero.vector, expected)
    assert_array_equal(zero.nuisance, base.nuisance)
    fitted.vector[0] = 999.0
    fitted.nuisance[0] = 999.0
    zero.vector[1] = 777.0
    zero.nuisance[1] = 777.0
    assert_array_equal(base.vector, np.arange(12, dtype=float))
    assert_array_equal(base.nuisance, [1.0, 2.0, 3.0])
    fresh = family.arm_context(base, "fitted-c")
    assert_array_equal(fresh.vector, base.vector)
    assert_array_equal(fresh.nuisance, base.nuisance)


def test_dispatch_has_same_exact_budgets_and_no_retry_after_nonstrict():
    calls = []

    def refitter(ctx, v, n, **options):
        calls.append(options)
        return dict(vector=v, nuisance=n, diagnostics=dict(evaluations=1000, accepted=False))

    def free_fitter(ctx, **options):
        calls.append(options)
        return (
            dict(
                vector=ctx.vector,
                nuisance=ctx.nuisance,
                diagnostics=dict(evaluations=1000, accepted=False),
            ),
            ctx,
            options["reused_profile"],
        )

    ctx = family.arm_context(context(), "zero-c")
    result, _ = family.one(ctx, "fixed", None, refitter=refitter)
    assert not result["diagnostics"]["accepted"] and len(calls) == 1
    result, _ = family.one(ctx, "joint", None, free_fitter=free_fitter, profile={"exact": "saved"})
    assert not result["diagnostics"]["accepted"] and len(calls) == 2
    assert all(c["max_evaluations"] == 1000 and c["max_seconds"] == 120 for c in calls)
    assert calls[1]["reused_profile"] == {"exact": "saved"}


def test_fingerprint_uses_real_public_bank_units_and_detects_design_mutation():
    bank = family.run.PositionOrbitBank(
        np.array([123]), np.array([0.0, 1.0]), np.ones((1, 2, 3)), np.zeros((1, 2, 3))
    )
    obs = SimpleNamespace(
        times_s=np.array([0.0]),
        measured_hz=np.array([5.0]),
        rf_hz=np.array([11e9]),
        receiver=np.array([0]),
        channel=np.array([4]),
    )
    raw = SimpleNamespace(
        design=np.ones((1, 5)),
        clock_design=np.ones((1, 1)),
        group_design=np.ones((1, 0)),
        baseline=np.zeros(1),
    )
    model = SimpleNamespace(mask=np.ones(1, bool), original=raw)
    ctx = replace(context(), bank=bank, observations=obs, model=model)
    before = family.fingerprint(ctx)
    assert before == family.fingerprint(ctx)
    raw.design[0, 0] = 2.0
    assert before != family.fingerprint(ctx)
