import numpy as np

from tools.pipeline_eval.variants import algo08_collapsed, v5_core


def test_paired_track_gate_rejection_does_not_mutate_prior_pair_mask():
    before = np.array([True, False, True, True, True, True])
    rows = [dict(component=str(i)) for i in range(3)]
    slices = [slice(a, a + 2) for a in (0, 2, 4)]
    pair = {arm: dict(gates=dict(tracks=[dict(row, compatible=int(row["component"]) != n)
                                         for row in rows]))
            for arm, n in zip(algo08_collapsed.ARMS, (0, 2), strict=True)}
    after, rejected = algo08_collapsed.paired_mask(before, rows, slices, pair)
    assert rejected == ["0", "2"]
    np.testing.assert_array_equal(after, [False, False, True, True, False, False])
    np.testing.assert_array_equal(before, [True, False, True, True, True, True])


def test_candidate_is_scoped_to_explicit_experimental_binding():
    original = v5_core.infer
    with algo08_collapsed.binding():
        assert v5_core.infer is algo08_collapsed.infer
    assert v5_core.infer is original
