import ctypes as ct
import math

import pytest

from tools.pipeline_eval.variants.experimental import receiver_build, receiver_carrier_eligibility


class State(ct.Structure):
    _fields_ = [
        ("valid", ct.c_int), ("rate", ct.c_int), ("count", ct.c_int),
        ("lo", ct.c_double), ("hi", ct.c_double), ("center", ct.c_double),
        ("eligible", ct.c_uint16 * 4096),
    ]


@pytest.fixture(scope="module")
def update(tmp_path_factory):
    binary = tmp_path_factory.mktemp("carrier-eligibility") / "receiver.so"
    receiver_carrier_eligibility.overlay(receiver_build.build)(binary, fftw=False, fma=False, reuse=False)
    library = ct.CDLL(str(binary))
    function = library.experimental_carrier_eligibility_update
    function.argtypes = [ct.POINTER(State), ct.c_int, ct.c_double, ct.c_double, ct.c_double]
    function.restype = ct.c_int
    return function


def original(rate, lo, hi, center):
    result = []
    for j in range(4096):
        hz = (j if j < 2048 else j - 4096) * float(rate) / 4096 + center
        if math.ceil((lo - hz) / rate) <= math.floor((hi - hz) / rate):
            result.append(j)
    return result


def test_carrier_cache_rebuilds_on_every_key_change_and_preserves_original_order(update):
    edge = 2_500_000 / 4096
    windows = [
        (2_500_000, -800_000., 800_000., 0.),
        (2_500_000, -800_000., 800_000., 177_500.),
        (10_000_000, -800_000., 800_000., 177_500.),
        (2_500_000, -1_251_000., -1_249_000., -17.5),
        (2_500_000, 1_249_000., 1_251_000., 17.5),
        (2_500_000, -edge, edge, 0.),
        (2_500_000, math.nextafter(-edge, 0.), edge, 0.),
        (2_500_000, math.nextafter(-edge, 0.), math.nextafter(edge, 0.), 0.),
        (2_500_000, math.nextafter(-edge, 0.), math.nextafter(edge, 0.), -0.),
        (2_500_000, 1., 2., 0.),
    ]
    state = State()
    for args in windows:
        assert update(ct.byref(state), *args) == 1
        assert list(state.eligible[:state.count]) == original(*args)
        saved = bytes(state)
        assert update(ct.byref(state), *args) == 0
        assert bytes(state) == saved


@pytest.mark.parametrize("rate,lo,hi,center", [
    (0, -5., 5., 0.), (2_500_000, 2., 1., 1.5), (2_500_000, -2., 2., float("nan")),
    (2_500_000, -2., float("inf"), 0.),
])
def test_invalid_bounds_do_not_change_existing_cache(update, rate, lo, hi, center):
    state = State()
    assert update(ct.byref(state), 2_500_000, -800_000., 800_000., 0.) == 1
    before = bytes(state)
    assert update(ct.byref(state), rate, lo, hi, center) == -1
    assert bytes(state) == before
