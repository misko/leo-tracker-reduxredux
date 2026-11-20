from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.qualification.complete_epoch_proxy_results import ALIAS_HZ, plant_counts
from tools.pipeline_eval.variants import complete_epoch_proxy as variant


def test_shortened_slices_keep_original_end_and_valid_short_anchors():
    assert variant.suffix(np.array([0, 50, 100]), np.array([44, 93, 108])).tolist() == [
        26,
        75,
        100,
    ]


def test_proposal_keeps_all_original_geometry_and_rescores_with_all_original_taps():
    samples = np.ones(200_000, dtype=np.complex128)
    template = np.ones(13_333)
    calls = []

    def native(x, t, frequencies, starts, stops, offsets, prefix, rate, epochs):
        assert x is samples and t is template
        assert prefix.size == x.size + 1
        calls.append((starts, stops, offsets, frequencies, epochs))
        return np.broadcast_to(
            np.arange(offsets[0], offsets[0] + epochs), (len(frequencies), epochs)
        )

    acquisition = SimpleNamespace(
        _native_acquisition=SimpleNamespace(folded_anchor_score_grid=native),
        FRAME_RATE_HZ=750,
        OFDM_SYMBOL_DURATION_S=4.4e-6,
        _constant_grid_step=lambda cfo: None,
        _power_prefix=lambda x: np.arange(x.size + 1),
    )
    all_frequencies = (0.0, 80_000.0)
    anchors = tuple(range(2, 302, 26))
    args = (samples, template, 10_000_000, all_frequencies, anchors, 128)

    def retain(cfo, score, count, separate_epochs, separate_cfo, epochs):
        assert cfo == all_frequencies and score.shape == (2, 128)
        assert (count, separate_epochs, separate_cfo, epochs) == (96, 5, 10_000.0, 128)
        return [(0.4, 20, 0.0), (0.0, 62, 0.0)]

    scores, detail = variant.propose(acquisition, args, all_frequencies, 5, 10_000.0, retain)
    coarse, exact = calls
    np.testing.assert_array_equal(coarse[1] - coarse[0], 18)
    np.testing.assert_array_equal(exact[1] - exact[0], 44)
    np.testing.assert_array_equal(coarse[1], exact[1])
    np.testing.assert_array_equal(exact[2], coarse[2] + 14)
    assert len(coarse[0]) == 12 and len(coarse[2]) == 15
    np.testing.assert_array_equal(coarse[3], exact[3])
    assert coarse[4] == 128 and exact[4] == 13
    assert detail["proposal_cells"] == 256 and detail["rescored_cells"] == 26
    assert detail["cap32_eligible_ranges"] == ((15, 26),)
    assert np.all(np.isnan(scores[0][:14])) and np.all(np.isnan(scores[0][27:]))
    np.testing.assert_array_equal(scores[1][14:27], np.arange(14, 27))


def test_signed_plants_separate_alias_compatibility_from_unfolded_cfo():
    def candidate(cfo, *, passed=True):
        return dict(
            integer_epoch_sample=731,
            fractional_epoch_offset_samples=0.1,
            fractional_tracking_cfo_hz=cfo,
            passed_fractional_margin_gate=passed,
        )

    assert plant_counts(
        "negative_high",
        [
            {"candidates": [candidate(-720_000 + ALIAS_HZ), candidate(720_000)]},
            {"candidates": [candidate(-720_000)]},
            {"candidates": [candidate(-720_000, passed=False)]},
        ],
    ) == dict(receiver_count=3, plant_alias_match_rx=2, plant_unfolded_match_rx=1)
