from rectangle_rank_control import affine_rank, paired_rank


def test_matching_columns_and_mismatched_pattern_control():
    words = [0, 0, 0, 1]
    assert affine_rank(words) == 1
    assert paired_rank(words, words, 1) == 1
    assert paired_rank(words, words, 1, 1) == 2
    assert affine_rank([w ^ 1 for w in words]) == 1
