from semantic_audit import counter_matches, polynomial_gcd


def test_polynomial_gcd_recovers_known_common_generator():
    # (x+1)(x^2+x+1)=x^3+1; (x+1)(x^2+1)=x^3+x^2+x+1.
    assert polynomial_gcd(0b1001, 0b1111) == 0b11
    assert polynomial_gcd(0, 0b1011) == 0b1011
    assert polynomial_gcd(0b1011, 0b1001) == 1


def test_counter_wrap_gaps_and_group_boundaries():
    rows = [
        dict(group="a", frame=f, word=f"{v:03b}" + "0" * 57) for f, v in [(0, 6), (1, 7), (3, 1)]
    ]
    rows.append(dict(group="b", frame=0, word="0" * 60))
    assert counter_matches(rows, 0, 3) == (2, 2)
    assert counter_matches(rows, 0, 3, invert=True) != (2, 2)
