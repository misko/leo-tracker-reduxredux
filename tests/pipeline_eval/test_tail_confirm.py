import numpy as np

from reports.ALGO08.v3.tail_confirm import bounds, decision, tables


def test_trailing_origins_disjoint_for_complete_epoch_and_fractional_domain():
    limits = [bounds(frame, epoch, offset)
              for frame in range(9, 14) for epoch in (0, 13332) for offset in (-1.5, 1.5)]
    assert min(lo for lo, _ in limits) == 120079
    assert max(hi for _, hi in limits) == 189577
    assert min(lo for lo, _ in limits)-40 >= 120000
    assert max(hi for _, hi in limits)+40 < 200000
    assert bounds(8, 0, -1.5)[0] < 120000
    assert bounds(14, 13332, 1.5)[1] >= 200000


def test_zero_ordinate_reproduces_original_glrt_normalization():
    rng = np.random.default_rng(2986)
    z = rng.normal(size=(5, 64)) + 1j*rng.normal(size=(5, 64))
    z[0] = 0  # An absent frame contributes no power and no normalization mass.
    normalization = (np.abs(z).sum(axis=1)**2).sum()
    direct = (np.abs(z.sum(axis=1))**2).sum()/normalization
    spectra = (np.abs(np.fft.fft(z, n=128, axis=1))**2).sum(axis=0)
    coefficients = np.conj(np.fft.fft(spectra))/128
    interpolated = np.zeros(512, dtype=np.complex128)
    interpolated[:64] = coefficients[:64]
    interpolated[-63:] = coefficients[-63:]
    original = np.fft.fft(interpolated)[0].real/normalization
    assert np.isclose(coefficients[64], 0, atol=1e-12)
    assert np.isclose(direct, original, rtol=1e-12)


def test_comparison_uses_signed_hz_and_distinguishes_full_selected_and_any():
    short = (0, 0, -1., -12_000., .4, .12)
    positive_tone = (0, 13332, 0., +12_000., .7, .12)
    matching_tone = (1, 13332, 0., -12_000., .3, .12)
    row = dict(mode="short_primary", lane=1, current=(short,), retained=(),
               raw20=(positive_tone, matching_tone), named=(positive_tone,))
    for row_totals in (tables([row]), tables([row], receiver=1)):
        assert row_totals["raw20_selected"]["short_only"] == 1
        assert row_totals["raw20_any"]["shared"] == 1
        assert row_totals["raw20_any"]["shared_retained"] == 0
        assert row_totals["named_selected"]["unmatched_both_positive"] == 1
    assert tables([row], receiver=0)["short_positive"] == 0


def test_screen_requires_both_shared_controls_and_northern_rejection():
    north = {"overall": {"named_selected": dict(short_only=2, short_only_retained=1, shared=21, shared_retained=20)}}
    weak = {"overall": {"raw20_selected": dict(shared=19, shared_retained=18)}}
    assert decision(north, weak) == dict(north_excess_rejection=True, north_shared_retention=True,
                                        weak_shared_retention=False)
    assert decision({}, {}) == dict(north_excess_rejection=False, north_shared_retention=False,
                                    weak_shared_retention=False)
