import numpy as np
from short_local import recover_pair


def test_short_recovery_requires_peer_word_and_complete_coverage():
    code = np.random.default_rng(8).choice([-1, 1], 60)
    mapping = np.tile(np.arange(60), (2, 1))
    values = code[mapping].astype(complex)
    assert recover_pair(values, values, mapping, mapping) is not None
    other = values.copy()
    other[:, 4] *= -1
    assert recover_pair(values, other, mapping, mapping) is None
    assert recover_pair(values[:, :-1], values[:, :-1], mapping[:, :-1], mapping[:, :-1]) is None
