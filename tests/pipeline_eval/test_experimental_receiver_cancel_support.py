import ctypes as ct
import subprocess
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.pipeline_eval.variants.experimental import receiver_cancel_support as audit
from tools.pipeline_eval.variants.experimental.receiver_build import build


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    work = tmp_path_factory.mktemp("cancel-support")
    receiver, measurements = work / "receiver.so", work / "audit.so"
    build(receiver, fftw=False, fma=False)
    source = Path(audit.__file__).with_suffix(".c")
    subprocess.run(["cc", "-O3", "-shared", "-fPIC", source, "-o", measurements], check=True)
    return ct.CDLL(str(receiver)), audit.SupportProbe(measurements)


def test_quarter_rate_centers_need_the_whole_clipped_fir_aperture():
    assert audit.fir_extent(0, 40) == (0, 0)
    assert audit.fir_extent(0, 41) == (0, 1)
    assert audit.fir_extent(99, 181) == (35, 36)
    assert audit.fir_extent(audit.SAMPLES - 44, audit.SAMPLES) == (49999, 50000)
    clean = audit.count_support([(0, audit.SAMPLES)])
    assert clean["clean_modes_rows"] == 14 and clean["used_fir_clean"] == 4740 + 43333


@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_actual_cancellation_mask_finishes_partial_frames_on_both_sides_of_wrap(native, edge):
    lib, probe = native
    cancel = lib.pilot_cancel
    cancel.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_void_p, ct.c_void_p,
                       ct.c_double, ct.c_double]
    cancel.restype = ct.c_int
    template = qin_edge_pilot_frame(30_000_000, edge).astype("<c8")
    raw = np.random.default_rng(47).integers(-2048, 2049, (audit.SAMPLES, 2, 2), dtype="<i2")
    for lane, epoch, hz in [
        (0, 0., -324_120.), (1, 2 / 3, 232_180.), (0, 39998 / 3, 636_018.),
    ]:
        assert cancel(raw.ctypes.data, probe.residual.ctypes.data, lane, template.ctypes.data,
                      probe.rotated.ctypes.data, epoch, hz) == 0
        np.testing.assert_array_equal(raw[:, 1 - lane], probe.residual[:, 1 - lane])
        expected = np.all(raw[:, lane] == probe.residual[:, lane], axis=-1)
        used = probe.equal_runs(raw.ctypes.data, probe.residual.ctypes.data, audit.SAMPLES, lane,
                                probe.runs.ctypes.data)
        observed = np.zeros(audit.SAMPLES, dtype=bool)
        for lo, hi in probe.runs[:used]:
            observed[lo:hi] = True
        np.testing.assert_array_equal(expected, observed)
        assert (~observed).any()
        for lo, hi in audit.guaranteed_clean_runs(epoch):
            assert observed[lo:hi].all()
        assert audit.count_support(probe.runs[:used].tolist())["clean_modes_rows"] == 0
