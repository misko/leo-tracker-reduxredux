import math

from pnt_variance_format import reference, run


def test_firmware_variance_boundaries_across_all_exponents():
    result = run(sorted({(e << 10) | m for e in range(64) for m in (0, 1, 511, 1022, 1023)}))
    assert result["cases"] == 320
    assert reference(0x8000) == 128
    assert reference(0x3C00) == 2 ** -10
    assert math.isnan(reference(65535))
