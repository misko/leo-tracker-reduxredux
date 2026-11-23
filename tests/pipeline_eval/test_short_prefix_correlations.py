"""Exercise exact prefix boundaries, native row identity and fallback."""

from contextlib import ExitStack
import ctypes as ct
import numpy as np
import pytest

from reports.ALGO08.v3.anchored_prefix_identity import transferable
from reports.ALGO08.v3 import short_cfo_refine as ref
from reports.ALGO08.v3.short_prefix_benchmark import build_full
from reports.ALGO08.v3.short_prefix_correlations import Audit, PREFIX, frame_geometry, same_bytes_by_frame, signature


@pytest.mark.parametrize("epoch, offset, ninth, full_count", [
    (0, 0.375, 0, 15),
    (11_000, -0.375, -1, 14),
    (13_332, 0.0, 1, 14),
])
def test_short_workspace_covers_eight_frames_even_when_ninth_class_changes(epoch, offset, ninth, full_count):
    starts, groups, sizes = frame_geometry(epoch, offset)
    np.testing.assert_array_equal(starts[:PREFIX], [epoch+(40_000*f+1)//3 for f in range(PREFIX)])
    np.testing.assert_array_equal(groups[:PREFIX], np.zeros(PREFIX, dtype=np.intc))
    assert groups[PREFIX] == ninth and len(starts) == full_count
    assert set(sizes) == {2816 if offset == 0 else 2831}


def test_both_pilot_rows_must_match_with_native_signed_zero():
    short = np.zeros((2, 8, 64), dtype=np.complex128)
    exact = short.copy()
    exact.view(np.float64)[1, 4, 9] = -0.0
    exact[0, 5, 62] = 1j
    assert same_bytes_by_frame(short, exact) == [True, True, True, True, False, False, True, True]


def test_recurrence_inventory_requires_witnessed_identical_guarded_mode_and_cfo():
    assert transferable(-200., -200., True, 0, False)
    assert not transferable(-200., -200., False, 0, False)
    assert not transferable(-200., -200., True, 1, False)
    assert not transferable(-200., -200., True, 0, True)
    assert not transferable(0., -0., True, 0, False)


def test_reused_prefix_matches_exact_integer_and_fractional_boundaries_and_wrong_seed(tmp_path):
    library, _ = build_full(tmp_path)
    verify = Audit(library)
    reuse = signature(verify.library, "short_cfo_reuse",
                      (ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_uint, ct.c_uint, ct.c_double,
                       ct.c_double, ct.c_double, ct.POINTER(ct.c_double), ct.POINTER(ct.c_int)), ct.c_int)
    iq = np.random.default_rng(9446).integers(-16000, 16000, (200_000, 2, 2), dtype=np.int16)
    for edge, digest in ref.PILOT_SHA.items():
        asset = np.frombuffer(ref.verified(ref.RELEASE/"assets"/f"{edge}.f32", digest), dtype="<f4")
        with ExitStack() as close:
            source, output = (ref.NativePath(ref.PAYLOAD/"receiver.so", asset, "full") for _ in range(2))
            for path in (source, output):
                close.callback(path.close)
            for index, (epoch, offset, cfo) in enumerate(((0, 0., 400_000.), (11_000, .375, -311_000.),
                                                          (13_332, -1.49999, 200_000.), (0, 9.999e-12, -55_000.))):
                lane = index % 2
                short = ((0, epoch, offset, cfo, .4, .1),)
                # Generate the exact original prefix for a geometry without
                # requiring a synthetic sinusoid to pass the live scout.
                expected = verify.diagnostics(source, iq, lane, short)
                assert expected is not None
                for seed, n in ((cfo, PREFIX), (cfo + 443.89, 0)):
                    values, used = (ct.c_double*8)(), ct.c_int()
                    assert not reuse(verify.context(output, 1), verify.context(source, 1), iq.ctypes.data, lane,
                                     epoch, offset, seed, cfo, values, ct.byref(used))
                    assert bytes(values) == bytes((ct.c_double*8)(*expected))
                    assert used.value == n
