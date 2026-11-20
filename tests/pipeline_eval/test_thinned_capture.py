from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import thinned_capture as variant


def test_uniform_frame_and_anchor_selection_matches_frozen_geometry():
    assert variant.strata(15, 2).tolist() == [3, 11]
    assert variant.strata(12, 4).tolist() == [1, 4, 7, 10]
    assert variant.strata(22, 4).tolist() == [2, 8, 13, 19]


def test_nomination_expands_periodically_but_keeps_original_physical_edge_rule():
    spans = variant.intervals(64, [(0.4, 1, 0.0), (0.2, 7, 80_000.0), (0.1, 34, 0.0)])
    assert spans == ((0, 14), (28, 41), (59, 64))
    assert variant.scored_interior(64, spans) == ((0, 13), (29, 40), (60, 64))


def test_proposal_pass_thins_support_and_rescore_keeps_original_samples_and_shape():
    samples, template = np.ones(200_000, dtype=np.complex128), np.ones(13_333)
    trace = []

    def fake_native(x, t, frequencies, starts, stops, offsets, prefix, rate, epochs):
        assert x is samples and t is template
        assert prefix.size == x.size + 1
        trace.append((len(starts), tuple(offsets.tolist()), epochs))
        epochs_full = np.arange(offsets[0], offsets[0] + epochs)
        return np.broadcast_to(epochs_full, (len(frequencies), epochs))

    acquisition = SimpleNamespace(
        _native_acquisition=SimpleNamespace(folded_anchor_score_grid=fake_native),
        FRAME_RATE_HZ=750,
        OFDM_SYMBOL_DURATION_S=4.4e-6,
        _constant_grid_step=lambda cfo: None,
        _power_prefix=lambda x: np.arange(len(x) + 1),
    )
    args = (samples, template, 10_000_000, (0.0, 80_000.0), tuple(range(2, 302, 26)), 128)
    scores, details = variant.propose(
        acquisition, args, args[3], 5, 10_000.0, lambda *_: [(0.4, 20, 0.0)]
    )
    assert trace[0] == (4, (40_000, 146_667), 128)
    assert trace[1][0] == 12 and trace[1][1][0] == 14 and len(trace[1][1]) == 15
    assert details["rescored_cells"] == 26
    assert np.all(np.isnan(scores[0][:14])) and np.all(np.isnan(scores[0][27:]))
    assert np.array_equal(scores[1][14:27], np.arange(14, 27))
