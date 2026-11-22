import ctypes as ct
import platform

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental.receiver_build import build


pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(platform.machine() != "x86_64", reason="x86 refinement bank build"),
]


class RefineRequest(ct.Structure):
    _fields_ = [("epoch", ct.c_int), ("hz", ct.c_double)]


REFINE_RESULT = ct.c_double * 4


@pytest.fixture(scope="module")
def refine_library(tmp_path_factory):
    output = tmp_path_factory.mktemp("refine_bank") / "receiver.so"
    build(output, fftw=False, fma=False, batch_refine=True)
    library = ct.CDLL(str(output))
    library.delay_refine.argtypes = [
        ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.c_double,
        ct.POINTER(ct.c_double),
    ]
    library.delay_refine_bank.argtypes = [
        ct.c_void_p, ct.c_void_p, ct.POINTER(RefineRequest), ct.c_int, ct.c_double,
        ct.c_double, ct.POINTER(REFINE_RESULT),
    ]
    return library


def check_bank(library, iq, pilot, seeds):
    args = (iq.ctypes.data, pilot.ctypes.data)
    limits = (-800000, 800000)
    requests = (RefineRequest * len(seeds))(*(RefineRequest(*seed) for seed in seeds))
    records = (REFINE_RESULT * len(seeds))()
    assert library.delay_refine_bank(*args, requests, len(seeds), *limits, records) == 0
    for (epoch, hz), actual in zip(seeds, records):
        original = REFINE_RESULT()
        assert library.delay_refine(*args, epoch, hz, *limits, original) == 0
        assert bytes(actual) == bytes(original)
    return records


@pytest.mark.parametrize("seeds", [
    [(7281, 531000)],
    [(4, 170201.5), (77, -521204), (4, -711204), (77, 170201.5)],
    [(13332, -411000), (7281, 735000), (13328, 735000), (0, -181000)],
    [(44, -785000), (44, -785000), (44, 309000), (44, 799320)],
    [(44, 0.0), (44, -0.0)],
    [(13332, -411000), (4, 100), (78, 100), (101, -100), (250, 411000)],
])
def test_bank_preserves_each_coarse_result_in_request_order(refine_library, seeds):
    rng = np.random.default_rng(3549)
    iq = rng.integers(-32768, 32768, 400000, dtype=np.int16).astype(np.float32)
    pilot = rng.normal(size=2 * 2816).astype(np.float32)
    check_bank(refine_library, iq, pilot, seeds)


def test_bank_breaks_ties_at_the_first_wrapped_offset(refine_library):
    iq = np.zeros(400000, np.float32)
    pilot = np.ones(2 * 2816, np.float32)
    seeds = [(0, -100000), (210, 45000), (210, 250000), (13332, 12000)]
    records = check_bank(refine_library, iq, pilot, seeds)
    assert [record[2] for record in records] == [13329, 206, 206, 13328]
