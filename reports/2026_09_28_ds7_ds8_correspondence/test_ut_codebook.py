import numpy as np
from compare_ut_codebook import recover_catalogue, slots


def test_separated_carriers_recover_same_word_without_fitting_validation():
    rng = np.random.default_rng(83)
    code = rng.choice([-1, 1], 60)
    a, b = np.arange(100, 104), np.arange(200, 204)
    za, zb = [code[slots(bins, np.arange(2, 302))].astype(complex)[None] for bins in [a, b]]
    rows = recover_catalogue(a, b, za, zb)
    assert len(rows) == 1
    assert rows[0]["word"] == "".join("1" if x > 0 else "0" for x in code)
    assert not recover_catalogue(a, b, za, -zb)


def test_random_signs_do_not_form_catalogue_entry():
    rng = np.random.default_rng(88)
    a, b = np.arange(100, 104), np.arange(200, 204)
    z = [rng.choice([-1.0, 1.0], (2, 300, 4)).astype(complex) for _ in range(2)]
    assert not recover_catalogue(a, b, *z)
