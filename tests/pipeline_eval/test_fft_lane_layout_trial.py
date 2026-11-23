import ctypes as ct
import subprocess
from pathlib import Path

import numpy as np

from reports.ALGO08.v3 import fft_lane_layout_trial as trial


def test_grouping_retains_operator_and_lane_order_for_partial_batches():
    raw = np.arange(5 * 3 * 2 * 2).reshape(5, 3, 2, 2)
    viewed = trial.grouped(raw, 2)
    assert viewed.shape == (6, 2, 2, 2)
    for group in range(2):
        for transform in range(3):
            np.testing.assert_array_equal(viewed[group * 3 + transform],
                                          raw[group * 2:group * 2 + 2, transform])


def test_interleaved_layout_keeps_independent_synthetic_tones(tmp_path):
    library = tmp_path / "native.so"
    source = Path(trial.__file__).with_name("fft_lane_layout.c")
    subprocess.run(["cc", "-O3", "-std=c11", "-fPIC", "-shared", "-D_POSIX_C_SOURCE=200809L",
                    source, "-o", library, "-lfftw3f"], check=True)
    dll = ct.CDLL(str(library))
    create = trial.wire(dll.fft_lane_create, [ct.c_int] * 3, ct.c_void_p)
    release = trial.wire(dll.fft_lane_free, [ct.c_void_p], None)
    arguments = [ct.c_void_p] * 3 + [ct.c_int, ct.c_int, ct.POINTER(ct.c_uint64)]
    measure = trial.wire(dll.fft_lane_measure, arguments, None)
    n, lanes = 4096, 4
    bins = [2, 23, 400, 1301]
    signal = np.exp(2j * np.pi * np.asarray(bins)[:, None] * np.arange(n) / n).astype(np.complex64)
    output = np.empty_like(signal)
    elapsed = (ct.c_uint64 * 2)()
    ctx = create(n, lanes, 0)
    assert ctx
    try:
        for mode in (0, 1):
            measure(ctx, signal.ctypes.data, output.ctypes.data, 1, mode, elapsed)
            assert list(np.argmax(np.abs(output), axis=1)) == bins
            assert elapsed[1] >= elapsed[0] > 0
    finally:
        release(ctx)
