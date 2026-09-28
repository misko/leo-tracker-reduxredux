import numpy as np
from short_header_parity import best_variable_check, check_score, pair_windows


def test_recovers_linear_code_relation_on_unseen_words():
    rng = np.random.default_rng(827)

    def fixture():
        words = []
        for _ in range(12):
            u = rng.integers(0, 2, 90, dtype=np.uint8)
            a = u[6:] ^ u[5:-1] ^ u[:-6]
            b = u[6:] ^ u[3:-3] ^ u[:-6]
            words.append(np.stack([a, b, u[6:]], axis=1).ravel())
        return pair_windows(words, 0, (0, 1))

    mask, score = best_variable_check(fixture())
    assert score == 1
    assert check_score(fixture(), mask) == 1


def test_constant_region_is_not_code_evidence():
    assert best_variable_check(np.zeros((80, 14), dtype=np.uint8)) is None
