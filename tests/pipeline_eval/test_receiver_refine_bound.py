import ctypes as ct
import platform
import subprocess

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental.receiver_build import HERE, PINNED, paired_fir, paired_refine
from tools.pipeline_eval.variants.experimental.receiver_refine_batch_overlay import kernel_overlay
from tools.pipeline_eval.variants.experimental.receiver_refine_bound import first_then_ranked, schedule


def candidate(score, gate, upper):
    return dict(score=score, gate=gate, upper=None if upper is None else [upper] * 4)


def test_ranking_keeps_earliest_equal_score_and_refines_overlapping_bounds():
    seeds = [candidate(5., 1, 9.), candidate(1., 1, 2.), candidate(5., 1, 5.),
             candidate(7., -3, 7.)]
    expected = dict(winner=0, pruned=[1], half_blocks=7, gate_stages=4)
    assert schedule(seeds, 0) == expected
    assert first_then_ranked(seeds) == expected


def test_first_failure_leaves_full_ranking_when_there_is_no_cutline():
    seeds = [candidate(5., -3, 5.), candidate(4., 1, 4.), candidate(6., 1, 6.),
             candidate(1., 1, 1.)]
    assert first_then_ranked(seeds) == dict(winner=2, pruned=[], half_blocks=8, gate_stages=4)
    assert schedule(seeds, 0) == dict(winner=2, pruned=[3], half_blocks=7, gate_stages=5)


def test_uncertified_candidate_receives_full_refinement():
    seeds = [candidate(5., 1, 5.), candidate(7., 2, None)]
    expected = dict(winner=1, pruned=[], half_blocks=4, gate_stages=3)
    assert first_then_ranked(seeds) == expected
    assert schedule(seeds, 0) == expected


class Request(ct.Structure):
    _fields_ = [("epoch", ct.c_int), ("hz", ct.c_double)]


Result = ct.c_double * 4


@pytest.fixture(scope="module")
def kernels(tmp_path_factory):
    scratch = tmp_path_factory.mktemp("refine-bound")
    source = PINNED / "tools/pipeline_eval/variants/delay_product_kernel.c"
    stock = kernel_overlay(paired_refine(paired_fir(source.read_text())))
    (scratch / source.name).write_text(stock)
    binary = scratch / "refine-bound.so"
    subprocess.run(["cc", "-shared", "-fPIC", "-O3", "-fopenmp-simd", "-ffp-contract=off",
                    "-I", scratch, "-I", HERE, "-I", source.parent,
                    HERE / "receiver_refine_bound.c", "-lm", "-o", binary], check=True)
    lib = ct.CDLL(str(binary))
    inputs = [ct.c_void_p, ct.c_void_p]
    lib.audit_delay_refine_bank.argtypes = [*inputs, ct.POINTER(Request), ct.c_int,
                                            ct.c_double, ct.c_double, ct.POINTER(Result)]
    lib.receiver_refine_prune.argtypes = [*inputs, Request, ct.c_double, ct.c_double, ct.c_double,
                                         ct.POINTER(ct.c_double)]
    lib.receiver_refine_enclosure.argtypes = [*inputs, Request, ct.c_double, ct.c_double,
                                             ct.POINTER(ct.c_double), ct.POINTER(ct.c_double)]
    return lib


@pytest.mark.hardware
@pytest.mark.skipif(platform.machine() != "x86_64", reason="x86 refinement build")
def test_native_bound_keeps_ties_and_wrapped_offsets(kernels):
    rng = np.random.default_rng(221406)
    iq = rng.integers(-32768, 32768, 400000, dtype=np.int16).astype(np.float32)
    pilot = rng.normal(size=2 * 2816).astype(np.float32)
    args = (iq.ctypes.data, pilot.ctypes.data)
    band = (-800000., 800000.)
    request = Request(9234, band[1])
    actual, upper, exact = Result(), Result(), Result()
    assert kernels.audit_delay_refine_bank(*args, ct.byref(request), 1, *band, ct.byref(exact)) == 0
    if not kernels.receiver_refine_enclosure(*args, request, *band, actual, upper):
        pytest.skip("asserting the parity arithmetic requires AVX2")
    assert bytes(actual) == bytes(exact)
    assert min(upper) >= exact[3]
    assert kernels.receiver_refine_prune(*args, request, *band, exact[3], actual) == 0
    assert bytes(actual) == bytes(exact)
    assert kernels.receiver_refine_prune(*args, request, *band, .25, actual) == 1
    assert kernels.receiver_refine_prune(*args, Request(0, -100000.), *band, .25, actual) == 2
    assert kernels.receiver_refine_prune(*args, request, *band, float("inf"), actual) == 2
