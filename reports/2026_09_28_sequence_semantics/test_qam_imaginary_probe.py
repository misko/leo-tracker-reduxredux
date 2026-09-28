import numpy as np
from qam_imaginary_probe import select_candidate


def test_evaluation_changes_cannot_change_candidate_or_polarity():
    rng = np.random.default_rng(90)
    candidates = rng.choice([-1, 1], size=(60, 240))
    observed = -candidates[17].copy()
    valid = np.ones(240, dtype=bool)
    before = select_candidate(candidates, observed, valid)
    observed[120:] *= -1
    after = select_candidate(candidates, observed, valid)
    assert before["candidate"] == after["candidate"] == 17
    assert before["polarity"] == after["polarity"] == -1
    assert before["errors"] == [0, 0]
    assert after["errors"] == [0, 120]
