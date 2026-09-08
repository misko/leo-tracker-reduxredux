"""Whole-dwell proposals are tested separately from detection/absence claims."""

import ctypes as ct

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.native_presence import build_window_ranker, pointer
from tools.presence_dwell import TimingProposal
from tools.presence_window_rank import NativeWindowRank, RankResult


@pytest.fixture(scope="module", params=["pruned", "all-cells"])
def library(tmp_path_factory, request):
    flags = ("-DLEO_PRESENCE_RANK_ALL_CELLS",) if request.param == "all-cells" else ()
    return build_window_ranker(tmp_path_factory.mktemp("window-rank") / "rank.so", cflags=flags)


def oracle(iq, rate, edge, bins):
    n = round(rate / 750)
    template = qin_edge_pilot_frame(rate, edge).astype(np.complex128)
    diff = np.roll(template, -4) * template.conj()
    position = np.arange(bins) * n / bins
    left = position.astype(int)
    fraction = position - left

    def project(values):
        x = values[left] + fraction * (values[(left + 1) % n] - values[left])
        x -= x.mean()
        energy = np.vdot(x, x).real
        return x / np.sqrt(energy) if energy else np.zeros(bins, dtype=np.complex128)

    reference = np.fft.fft(project(diff))
    scores, epochs = [], []
    samples = iq[:, 0].astype(float) + 1j * iq[:, 1]
    for values in samples.reshape(6, rate // 50):
        products = values[4:] * values[:-4].conj()
        folded, support = np.zeros(n, dtype=np.complex128), np.zeros(n)
        for frame in range(15):
            start = round(frame * rate / 750)
            chunk = products[start : start + n]
            folded[: len(chunk)] += chunk
            support[: len(chunk)] += 1
        folded /= np.maximum(support, 1)
        correlation = np.fft.ifft(np.fft.fft(project(folded)) * reference.conj())
        best = int(np.argmax(np.abs(correlation)))
        scores.append(abs(correlation[best]))
        epochs.append(round(best * n / bins) % n)
    return np.array(scores), np.array(epochs)


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("bins", [512, 1024, 2048, 4096, 8192])
def test_scores_and_window_order_match_independent_double_oracle(library, rate, edge, bins):
    # Includes CI16 extrema, for which int32 complex-product sums overflow.
    rng = np.random.default_rng(127)
    iq = rng.integers(-32768, 32768, (rate * 120 // 1000, 2), dtype=np.int16)
    before = iq.tobytes()
    expected, epochs = oracle(iq, rate, edge, bins)
    with NativeWindowRank(library, rate, edge, bins) as native:
        result = native.run(iq)
        again = native.run(iq)
    np.testing.assert_allclose(result.scores, expected, atol=2e-7, rtol=2e-6)
    np.testing.assert_array_equal(result.projected_epoch_samples, epochs)
    np.testing.assert_array_equal(result.order, np.argsort(-expected, kind="stable"))
    np.testing.assert_array_equal(result.scores, again.scores)
    assert result.total_cpu_ms >= result.fold_cpu_ms + result.correlation_cpu_ms
    assert iq.tobytes() == before


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_single_window_api_preserves_whole_dwell_scores_and_failed_output(library, rate):
    rng = np.random.default_rng(451)
    iq = rng.integers(-32768, 32768, (6 * rate // 50, 2), dtype=np.int16)
    with NativeWindowRank(library, rate, "lower", 512) as native:
        result = native.run(iq)
        function = native.library.leo_presence_rank_window_ci16
        function.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.POINTER(TimingProposal)]
        for index, window in enumerate(iq.reshape(6, rate // 50, 2)):
            out = TimingProposal()
            assert function(native.workspace, pointer(window), len(window), ct.byref(out)) == 0
            assert out.score == result.scores[index]
            assert out.epoch == result.projected_epoch_samples[index]
        before = bytes(out)
        assert function(native.workspace, pointer(iq), len(iq), ct.byref(out)) == -1
        assert bytes(out) == before


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("slice_index", range(6))
def test_signal_in_each_temporal_slice_is_ranked_first(library, rate, slice_index):
    rng = np.random.default_rng(42)
    values = 20 * (rng.normal(size=rate * 120 // 1000) + 1j * rng.normal(size=rate * 120 // 1000))
    window = rate // 50
    template = qin_edge_pilot_frame(rate, "upper")
    for frame in range(15):
        start = 317 + round(frame * rate / 750)
        stop = min(start + len(template), window)
        if stop > start:
            values[slice_index * window + start : slice_index * window + stop] += (
                1000
                * template[: stop - start]
                * np.exp(2j * np.pi * 312345 * np.arange(start, stop) / rate)
            )
    iq = np.rint(np.column_stack((values.real, values.imag))).astype(np.int16)
    with NativeWindowRank(library, rate, "upper", 2048) as native:
        result = native.run(iq)
    assert result.order[0] == slice_index
    assert result.scores[slice_index] > 0.3


@pytest.mark.parametrize("level", [0, 32767, -32768])
def test_constant_lag_input_has_zero_score_and_stable_ties(library, level):
    iq = np.full((300000, 2), level, dtype=np.int16)
    with NativeWindowRank(library, 2500000, "lower", 2048) as native:
        result = native.run(iq)
    assert list(result.scores) == [0] * 6
    assert list(result.order) == list(range(6))


def test_invalid_geometry_is_unknown_and_does_not_mutate_result(library):
    iq = np.zeros((300000, 2), dtype=np.int16)
    with NativeWindowRank(library, 2500000, "lower", 2048) as native:
        result = RankResult()
        ct.memset(ct.byref(result), 0x31, ct.sizeof(result))
        before = bytes(result)
        for count in (0, 50000, 299999, 300001, 600000):
            assert (
                native.library.leo_presence_rank_ci16(
                    native.workspace, pointer(iq), count, ct.byref(result)
                )
                == -1
            )
            assert bytes(result) == before
        for values in (iq[:-1], iq.astype(float), iq[:, 0], iq.reshape(6, -1, 2)):
            with pytest.raises(ValueError):
                native.run(values)
    with pytest.raises(ValueError, match="closed"):
        native.run(iq)
    for rate, edge, bins in (
        (3000000, "lower", 2048),
        (2500000, "bogus", 2048),
        (2500000, "lower", 1234),
    ):
        with pytest.raises(ValueError):
            NativeWindowRank(library, rate, edge, bins)


@pytest.mark.parametrize("scale", [0, 1e-30, float("nan"), float("inf"), 100])
def test_degenerate_or_unrepresentable_template_is_rejected(library, scale):
    with np.errstate(invalid="ignore"):
        template = np.asarray(qin_edge_pilot_frame(2500000, "lower"), dtype=np.complex128) * scale
    with NativeWindowRank(library, 2500000, "lower", 512) as native:
        assert not native.library.leo_presence_rank_create(
            2500000, pointer(template), len(template), 512
        )
