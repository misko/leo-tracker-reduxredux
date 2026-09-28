from header_block_rank import rank


def test_rank_bound_and_early_rejection():
    basis = [1 << i for i in range(32)]
    assert rank(basis + [3, 7, 31]) == 32
    assert rank(basis + [1 << 100], stop=33) == 33
    assert rank([0, 0]) == 0
