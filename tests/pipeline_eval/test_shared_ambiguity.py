import ctypes as ct

import numpy as np
import pytest

from reports.ALGO08.v3.shared_ambiguity_trial import (
    Kernel, build, needed_rank, parseval_bound, signed_span, steering, wall_budget_rank,
)


def test_weighted_dirichlet_span_matches_explicit_signed_bank():
    code = np.array([1., 2j, -1. - 1j, 2., -2j, .5j])
    code /= np.linalg.norm(code)
    bins = np.arange(-5, 6)
    basis, optimal = signed_span(code, fft_size=32, bins=bins)
    explicit = steering(code, bins, rate=32)
    captured = np.cumsum(np.mean(abs(basis.conj().T @ explicit)**2, axis=1))
    np.testing.assert_allclose(optimal, captured, atol=1e-14)
    np.testing.assert_allclose(optimal[-1], 1., atol=1e-14)
    assert np.all(optimal <= parseval_bound(code, fft_size=32, bins=bins) + 1e-14)
    assert needed_rank(optimal, .9) <= len(code)
    assert needed_rank([.1, .88, .91, 1.], .9) == 3


def test_budget_separates_complete_callback_from_kernel_clocks():
    values = {32: {"batched": {"median_cpu_ms": .21}, "stream": {"median_cpu_ms": .16}},
              64: {"batched": {"median_cpu_ms": .39}, "stream": {"median_cpu_ms": .32}}}
    assert wall_budget_rank(values, .689, .368, 1.5) == 32
    assert wall_budget_rank(values, .689, 0., 1.5) == 64
    assert wall_budget_rank(values, .581, .368, 1.5) == 0


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    output = tmp_path_factory.mktemp("shared-ambiguity") / "kernel.so"
    build(output)
    return ct.CDLL(str(output))


@pytest.mark.parametrize("batch", [False, True])
def test_shared_native_fft_reproduces_cyclic_lag_and_signed_carriers(compiled, batch):
    rng = np.random.default_rng(69)
    size, taps = 60, 25
    pilot = rng.normal(size=taps) + 1j * rng.normal(size=taps)
    filters = steering(pilot, np.array([-11., 2., 10.]), rate=size).T
    spectra = np.ascontiguousarray(np.fft.fft(filters, n=size, axis=1), dtype=np.complex64)
    signal = (rng.normal(size=size) + 1j * rng.normal(size=size)).astype(np.complex64)
    output = np.empty((len(filters), size), dtype=np.complex64)
    with Kernel(compiled, size, len(filters), batch) as bank:
        bank.run(signal, spectra, output)
    lags = (0, 5, size - 1)
    expected = [[np.vdot(row, signal[(epoch + np.arange(taps)) % size]) for epoch in lags]
                for row in filters]
    np.testing.assert_allclose(output[:, lags] / size, expected, atol=3e-6, rtol=3e-6)
