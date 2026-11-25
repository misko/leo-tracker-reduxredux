import ctypes as ct
import os
from pathlib import Path
import subprocess

import numpy as np
import pytest

from reports.ALGO08.v3.sparse8_lag_prefix import ordered_prefix, overlay
from reports.ALGO08.v3.sparse8_lag_prefix_measure import allowed_inputs, summary
from reports.ALGO08.v3 import sparse8_lag_prefix_ram as ram


ROOT = Path(__file__).resolve().parents[2]
SPECTRAL = ROOT / "tools/pipeline_eval/variants/experimental/receiver_spectral_vectors.inc"
FIXTURE = Path(__file__).with_name("sparse8_lag_prefix_fixture.c")
LAGS = (2, 4, 6, 11, 18, 28, 44, 74)


@pytest.fixture(scope="module")
def kernels(tmp_path_factory):
    work = tmp_path_factory.mktemp("sparse8-lag-prefix")
    changed = work / "candidate.inc"
    changed.write_bytes(ordered_prefix(SPECTRAL.read_bytes()))
    libs = []
    for index, implementation in enumerate((SPECTRAL, changed)):
        library = work / f"kernel-{index}.so"
        subprocess.run(["cc", "-O3", "-std=c11", "-fPIC", "-shared", "-ffp-contract=off", "-fno-math-errno",
                        "-fno-strict-aliasing", f'-DSPECTRAL_IMPL="{implementation}"', str(FIXTURE),
                        "-lfftw3f", "-lm", "-o", str(library)], check=True)
        binary = ct.CDLL(str(library))
        binary.has_avx2.argtypes = ()
        binary.has_avx2.restype = ct.c_int
        if not binary.has_avx2():
            pytest.skip("This component requires the native receiver's AVX2 path")
        binary.lag_products.argtypes = (ct.c_void_p,) * 4 + (ct.c_int,) * 3
        binary.lag_products.restype = None
        binary.lag_timing.argtypes = (ct.c_void_p,) * 6
        binary.lag_timing.restype = ct.c_int
        libs.append(binary)
    return libs


def inputs(width):
    rng = np.random.default_rng(11678)
    mixed = np.ldexp(rng.standard_normal((2, width, 2), dtype=np.float32),
                     rng.integers(-22, 20, size=(2, width, 2))).astype(np.float32)
    mixed[:, ::5, 0] = -0.
    mixed[:, ::11, 1] = 0.
    return mixed


@pytest.mark.hardware
@pytest.mark.parametrize(("width", "size", "lags"), [(4740, 4800, LAGS), (9, 16, range(1, 9)),
                                                    (18964, 19200, (26, 298))])
def test_production_and_tail_products_keep_ordered_prefix_bytes(kernels, width, size, lags):
    a, b = inputs(width)
    for lag in lags:
        output = []
        for binary in kernels:
            values = np.full((size, 2), np.nan, dtype=np.float32)
            sums = np.full(width + 1, np.nan, dtype=np.float64)
            binary.lag_products(values.ctypes.data, sums.ctypes.data, a.ctypes.data, b.ctypes.data, width, lag, size)
            assert np.count_nonzero(values[width-lag:].view(np.uint32)) == 0
            assert np.isnan(sums[width-lag+1:]).all()
            output.append((values.tobytes(), sums.tobytes()))
        assert output[0] == output[1]


@pytest.mark.hardware
def test_prefix_does_not_reassociate_small_terms_or_change_nonfinite_class(kernels):
    # At lag one, the first product has energy 2^26. Each of the later powers
    # is only 2^-28 and rounds away in the required one-at-a-time binary64 sum.
    a, b = np.zeros((2, 12, 2), dtype=np.float32)
    a[0, 0], a[1, 0], a[3:, 0] = 1., 8192., 2.**-7
    for binary in kernels:
        out = np.empty((16, 2), dtype=np.float32)
        sums = np.empty(12, dtype=np.float64)
        binary.lag_products(out.ctypes.data, sums.ctypes.data, a.ctypes.data, b.ctypes.data, 12, 1, 16)
        assert sums[1] == 2.**26
        assert np.all(sums[1:] == 2.**26)
        assert sums[-1] != 2.**26 + 8 * 2.**-28
    a[7, 0] = np.inf
    results = []
    for binary in kernels:
        out = np.empty((16, 2), dtype=np.float32)
        sums = np.empty(12, dtype=np.float64)
        binary.lag_products(out.ctypes.data, sums.ctypes.data, a.ctypes.data, b.ctypes.data, 12, 1, 16)
        for values in (out.ravel(), sums):
            results.append((np.isnan(values).tobytes(), values[~np.isnan(values)].tobytes()))
    assert results[:2] == results[2:]


@pytest.mark.hardware
@pytest.mark.parametrize("zero", [False, True])
def test_full_eight_lags_keep_scores_and_all_circular_rank_ties(kernels, zero):
    a, b = inputs(4740)
    f = inputs(4 * 4800).reshape(8, 4800, 2)
    if zero:
        a.fill(-0.)
        b.fill(0.)
    results = []
    for binary in kernels:
        scores = np.empty(3333, dtype=np.float64)
        excluded = scores.copy()
        peaks = np.empty(12, dtype=np.int32)
        assert binary.lag_timing(*(x.ctypes.data for x in (a, b, f, scores, excluded, peaks))) == 0
        results.append((scores.tobytes(), excluded.tobytes(), peaks.tobytes()))
        if zero:
            assert np.array_equal(peaks, np.arange(0, 36, 3))
            assert np.all(excluded[-2:] == -1.)
    assert results[0] == results[1]


def test_overlay_refuses_changed_source_before_creating_output(tmp_path):
    with pytest.raises(ValueError, match="spectral kernel"):
        ordered_prefix(SPECTRAL.read_bytes() + b"\n")
    source = tmp_path / "wrong.c"
    source.write_text("different timing unit")
    target = tmp_path / "unused"
    with pytest.raises(ValueError, match="timing unit"):
        overlay(source, SPECTRAL, target)
    assert not target.exists()


def test_timing_summary_preserves_orders_and_detector_positivity():
    records = [dict(round=0, first="control", factor_hex="a0", cpu_ns=dict(control=100, candidate=80)),
               dict(round=0, first="candidate", factor_hex="", cpu_ns=dict(control=400, candidate=405)),
               dict(round=1, first="candidate", factor_hex="a0", cpu_ns=dict(control=99, candidate=88)),
               dict(round=1, first="control", factor_hex="", cpu_ns=dict(control=405, candidate=415))]
    result = summary(records)
    assert result["all"]["all_orders"]["median_paired_saving_ns"] == 4
    assert result["positive"]["by_first"]["candidate"]["median_paired_saving_ns"] == 11
    assert result["empty"]["by_first"]["control"]["median_paired_saving_ns"] == -10


def test_short_timing_job_admits_only_enrolled_local_waveforms_read_only(tmp_path):
    local = tmp_path / "verified.ci16"
    allowed_inputs("open", (local, "rb", os.O_RDONLY), {local})
    for path, flag in ((Path("/srv/bulk/other"), os.O_RDONLY), (tmp_path / "other.ci16", os.O_RDONLY),
                      (local, os.O_RDWR)):
        with pytest.raises(ValueError):
            allowed_inputs("open", (path, "rb", flag), {local})
    with pytest.raises(ValueError):
        allowed_inputs("socket.connect", (), {local})


def test_ram_namespace_uses_positive_binds_and_a_read_only_root(tmp_path, monkeypatch):
    available = [tmp_path / "signed.ci16", tmp_path / "receiver.so"]
    monkeypatch.setattr(ram, "paths", lambda *_: (None, None, None, None, available))
    cli = ram.command(tmp_path, "probe", tmp_path, "pin")
    assert "--unshare-all" in cli and "--disable-userns" in cli and "--clearenv" in cli
    assert cli[cli.index("--cap-drop") + 1] == "ALL"
    assert "/srv/bulk" not in cli and "/mnt/qnap01" not in cli and "/srv/postgres-nvme" not in cli
    for file in available:
        start = cli.index(str(file))
        assert cli[start - 1:start + 2] == ["--ro-bind", str(file), str(file)]
    readonly = [cli[i+1] for i, key in enumerate(cli) if key == "--remount-ro"]
    assert readonly == ["/tmp", "/"]
