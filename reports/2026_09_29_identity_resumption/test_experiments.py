import numpy as np
from corpus_identity import contrast, features, separation_bin
from within_visit import counter_audit, counter_templates


def test_relative_features_cancel_common_phase_and_polarity():
    rng = np.random.default_rng(31)
    z = rng.normal(size=(2, 6, 4)) + 1j * rng.normal(size=(2, 6, 4))
    original, rotated = features(z), features(z * np.exp(1.7j))
    assert not np.allclose(original[0], rotated[0])
    assert np.allclose(original[1], rotated[1])
    assert np.allclose(original[2], rotated[2])


def test_stratification_does_not_credit_unmatched_identity_pairs():
    labels = np.array([1, 1, 2, 3])
    i, j = np.array([0, 0, 2]), np.array([1, 2, 3])
    scores = np.array([[.9], [.1], [.8]])
    effect, used = contrast(labels, i, j, [np.array([0]), np.array([1, 2])], scores)
    assert effect is None and used == []
    effect, used = contrast(labels, i, j, [np.array([0, 1, 2])], scores)
    assert np.allclose(effect, [.45]) and used == [0]


def test_counter_uses_physical_frame_gaps_and_transfers_real_counter():
    frames = np.array([0, 1, 4, 7, 9, 12, 13, 15, 18, 20, 24, 27, 29, 30, 31, 33])
    patterns, labels = counter_templates(frames)
    k = labels.index((8, 0, False))
    assert np.array_equal(patterns[k], frames % 8 >= 4)
    train = np.arange(64)
    test = np.arange(64, 128)
    result = counter_audit((train[:, None] % 8 >= 4), (test[:, None] % 8 >= 4), train, test)
    assert result["heldout_accuracy"] == [1.0]
    assert separation_bin(9) != separation_bin(10)
