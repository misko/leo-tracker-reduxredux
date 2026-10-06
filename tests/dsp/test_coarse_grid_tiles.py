"""Scientific CFO lanes survive register-sized execution tiles unchanged."""

import numpy as np
import pytest

from leo.analysis.starlink import acquisition as a


@pytest.mark.hardware
@pytest.mark.parametrize("rate", [1_250_000, 2_500_000, 5_000_000, 10_000_000])
@pytest.mark.parametrize("count", [13, 21, 24, 25])
def test_tiled_grid_matches_unpartitioned_native_grid(rate, count):
    if a._folded_anchor_score_grid_backend() != "avx2_fma":
        pytest.skip("requires the compiled acquisition extension and AVX2/FMA CPU")
    rng = np.random.default_rng(94)
    template = np.asarray(a.qin_edge_pilot_frame(rate, "lower"), dtype=np.complex128)
    values = rng.normal(size=len(template) * 2 + 31).astype(np.complex128)
    values += 1j * rng.normal(size=len(values))
    values[: len(template) // 2] = 0
    frequencies = tuple(np.linspace(-400_000, 400_000, count))
    # Fractional final frame and zero-energy cells exercise support boundaries.
    args = (values, template, rate, frequencies, (2, 28, 288), round(rate / 750))
    expected = a._folded_anchor_score_grid_native(*args, backend="avx2_fma")
    actual = a._folded_anchor_score_grid_native(*args)
    # The register kernel uses explicit FMA; the generic compiled loop can
    # round differently by a few ulps. Preserve the existing native-oracle
    # tolerance, and separately require identical winning epochs.
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(np.argmax(actual, axis=1), np.argmax(expected, axis=1))


def test_tiling_is_only_enabled_for_auto_avx2_and_preserves_arbitrary_frequencies(monkeypatch):
    class Native:
        def __init__(self):
            self.calls = []

        def folded_anchor_score_grid(self, values, template, frequencies, *args):
            self.calls.append(frequencies.copy())
            return np.broadcast_to(frequencies[:, None], (len(frequencies), args[-1])).copy()

        def folded_anchor_score_grid_backend(self):
            return "avx2_fma"

    native = Native()
    monkeypatch.setattr(a, "_native_acquisition", native)
    frequencies = tuple(float(i * i - 40) for i in range(25))
    args = (np.ones(200), np.ones(100), 1_250_000, frequencies, (2,), 10)
    result = a._folded_anchor_score_grid_native(*args)
    assert [len(v) for v in native.calls] == [12, 12, 12]
    np.testing.assert_array_equal(np.asarray(result)[:, 0], frequencies)
    assert np.all(native.calls[-1] == frequencies[-1])
    native.calls.clear()
    monkeypatch.setattr(native, "folded_anchor_score_grid_backend", lambda: "portable")
    a._folded_anchor_score_grid_native(*args)
    assert len(native.calls) == 1
    np.testing.assert_array_equal(native.calls[0], frequencies)
