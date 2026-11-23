import ctypes as ct
import subprocess

import numpy as np
import pytest

from reports.ALGO08.v3.receiver_polyphase_trial import POLYPHASE, match_factors, outcomes, retry_cost


@pytest.mark.parametrize("both", [0, 1])
def test_native_fold_matches_full_inverse_on_retained_epochs(tmp_path, both):
    source = POLYPHASE.read_text()
    fold = source[source.index("static void fold_polyphase("):
                  source.index("static void polyphase_scores(")]
    wrapper = tmp_path / "fold.c"
    wrapper.write_text(f"""
#define timing_fold_both {both}
typedef struct {{ float re, im; }} Sample;
static Sample multiply(Sample a, Sample b) {{
    return (Sample){{a.re * b.re - a.im * b.im, a.re * b.im + a.im * b.re}};
}}
{fold}
void fold(Sample *values, const Sample *rotation, int half) {{
    fold_polyphase(values, rotation, half);
}}
""")
    obj = tmp_path / "fold.so"
    subprocess.run(["cc", "-O3", "-shared", "-fPIC", "-ffp-contract=off",
                    wrapper, "-o", obj], check=True)
    native = ct.CDLL(str(obj)).fold
    native.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int]
    native.restype = None
    n = 4800
    half = n // 2
    rot = np.exp(2j * np.pi * np.arange(half) / n).astype(np.complex64)
    rng = np.random.default_rng(271828)
    for signal in (
        np.zeros(n, dtype=np.complex64),
        np.exp(-2j * np.pi * 3331 * np.arange(n) / n).astype(np.complex64),
        (rng.normal(size=n) + 1j * rng.normal(size=n)).astype(np.complex64),
    ):
        original = np.fft.ifft(signal)
        folded = signal.copy()
        native(folded.ctypes.data, rot.ctypes.data, half)
        even = np.fft.ifft(folded[:half]) / 2
        np.testing.assert_allclose(even, original[::2], atol=5e-8, rtol=2e-6)
        if both:
            odd = np.fft.ifft(folded[half:]) / 2
            np.testing.assert_allclose(odd, original[1::2], atol=5e-8, rtol=2e-6)
        else:
            np.testing.assert_array_equal(folded[half:], signal[half:])


def factor(rank, epoch, hz):
    return rank, epoch, 0., hz, .05, .01


def test_matches_wrapped_epoch_once_and_checks_signed_cfo():
    left = (factor(0, 1, -123_000.), factor(1, 13332, -123_020.))
    right = (factor(0, 0, -123_010.), factor(1, 13332, 123_020.))
    assert match_factors(left, right) == ((0, 0),)
    assert match_factors(left, right[:1]) == ((0, 0),)
    assert match_factors(left, (factor(0, 13332, -123_020.),)) == ((1, 0),)


def test_lost_residual_and_selected_observation_cost_whole_lane_retry():
    primary, residual, replacement = factor(0, 934, 17_000.), factor(1, 2230, -30_000.), (
        factor(1, 2230, 30_000.))
    pairs = [[("visit", 0, (primary, residual), (1, 1, [2, 6]))],
             [("visit", 0, (primary, replacement), (0, None, [2, 0]))]]
    result = outcomes(pairs)
    assert result["counts"]["matched_by_rank"] == [1, 0]
    assert result["counts"]["matching_continued"] == 0
    retries = retry_cost(pairs, [[300_000]], [[.0003, .0002]])
    assert retries["oracle_factor_availability"]["lanes"] == 1
    assert retries["oracle_factor_availability"]["candidate_over_installed_cpu_after_retry"] == [
        pytest.approx(5 / 3)]
    assert retries["fewer_than_two"]["lanes"] == 0
