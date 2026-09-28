from audit import ALIAS_SPACING_HZ, CANONICAL_RF_HZ, exported_measured_hz


def test_frequency_shift_scales_with_rf_and_alias_spacing() -> None:
    actual_rf_hz = 11_440_000_000.0
    native = 792_700.0
    shifted = native + 1_000.0

    baseline = exported_measured_hz(native, actual_rf_hz, 3)
    result = exported_measured_hz(shifted, actual_rf_hz, 3)

    assert abs((result - baseline) - 1_000.0 * CANONICAL_RF_HZ / actual_rf_hz) < 1e-9
    assert ALIAS_SPACING_HZ == 227_272.72727272726


def test_cached_examples_reproduce_export() -> None:
    cases = (
        (108_143.54826419879, 0, 105_874.8024964184),
        (106_899.61131580087, 0, 104_656.9621273575),
        (105_488.91370869041, 0, 103_275.85957494166),
        (792_700.0, 3, 108_555.62619198998),
        (791_364.7954985208, 3, 107_248.43297375855),
        (789_981.8032041385, 3, 105_894.4545037339),
    )

    for native, alias, expected in cases:
        assert abs(exported_measured_hz(native, 11_440_000_000.0, alias) - expected) < 2e-10
