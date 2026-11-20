import ctypes as c

import numpy as np
import pytest

from tools.pipeline_eval.qualification import verifier_integration_results as evidence
from tools.pipeline_eval.qualification import verifier_integration_trial as trial
from tools.pipeline_eval.variants import verifier_integration as module


@pytest.fixture(scope="module")
def bridge(tmp_path_factory):
    path = trial.build(tmp_path_factory.mktemp("verifier-integration"))["path"]
    dll = c.CDLL(path)
    dll.portable_verifier_create.argtypes = (c.c_void_p, c.c_void_p)
    dll.portable_verifier_create.restype = c.c_void_p
    dll.portable_verifier_free.argtypes = (c.c_void_p,)
    dll.portable_verifier_free.restype = None
    dll.verifier_integration_batch.argtypes = (
        c.c_void_p,
        c.c_void_p,
        c.c_uint,
        c.POINTER(module.Seed),
        c.c_uint,
        c.c_double,
        c.c_double,
        c.c_double,
        c.POINTER(module.Result),
    )
    dll.verifier_integration_batch.restype = c.c_int
    return dll


def test_stereo_bridge_reuses_loaded_lane_for_same_context(bridge):
    template = np.ones(13_333, dtype=np.complex128)
    raw = np.zeros((200_000, 2, 2), dtype="<i2")
    context = bridge.portable_verifier_create(template.ctypes.data, template.ctypes.data)
    assert context
    try:
        seed = module.Seed(41, 161, -40_000.0, -40_000.0)
        initial, repeated = module.Result(), module.Result()
        assert (
            bridge.verifier_integration_batch(
                context,
                raw.ctypes.data,
                0,
                c.byref(seed),
                1,
                0,
                -800_000,
                800_000,
                c.byref(initial),
            )
            == 0
        )
        assert (
            bridge.verifier_integration_batch(
                context, None, 0, c.byref(seed), 1, 0, -800_000, 800_000, c.byref(repeated)
            )
            == 0
        )
        assert bytes(initial) == bytes(repeated)
        assert initial.integer_exact == initial.integer_control == 0
        assert initial.flags & module.GUARD
        assert not initial.flags & module.FRAC_COMPLETE
    finally:
        bridge.portable_verifier_free(context)


def test_rank_and_gate_disagreement_survives_numeric_tolerance():
    first = dict(integer_epoch_sample=150, fractional_margin=0.024, passed=False)
    second = dict(integer_epoch_sample=154, fractional_margin=0.026, passed=True)
    result = evidence.differences([first, second], [second, first])
    assert {row["path"] for row in result["mismatches"] if row["reason"] == "discrete"} == {
        "$[0].integer_epoch_sample",
        "$[0].passed",
        "$[1].integer_epoch_sample",
        "$[1].passed",
    }
    tolerant = evidence.differences(first, dict(first, fractional_margin=0.024 + 1e-13))
    assert not tolerant["bitwise_equal"]
    assert not tolerant["mismatches"]
