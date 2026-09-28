from phase_rank import binary_rank, polynomial_gcd


def test_affine_six_bit_code_has_rank_six_after_offset_removal():
    generators = [1 << (i * 3) for i in range(6)]
    offset = 0b101010
    words = [
        offset ^ sum(g for i, g in enumerate(generators) if value >> i & 1) for value in range(64)
    ]
    assert binary_rank([word ^ words[0] for word in words]) == 6
    assert binary_rank([0, 3, 5, 6, 3]) == 2


def test_polynomial_gcd_known_common_factor():
    assert polynomial_gcd(0b101, 0b11) == 0b11
    assert polynomial_gcd(0b111, 0b11) == 1
