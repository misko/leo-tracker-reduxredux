from census import eligible


def test_strict_duration_and_inclusive_rate():
    assert not eligible({"times_s": [0, 3]}, 5_000_000)
    assert eligible({"times_s": [5, 1, 4]}, 5_000_000)
    assert not eligible({"times_s": [0, 10]}, 2_500_000)
