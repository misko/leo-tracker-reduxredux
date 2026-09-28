"""Pure unit mapping used by the DS7 frequency-units audit."""

CANONICAL_RF_HZ = 11_200_000_000.0
ALIAS_SPACING_HZ = 1.0 / 4.4e-6


def exported_measured_hz(
    native_tracking_cfo_hz: float,
    actual_rf_hz: float,
    relative_alias_index: int,
) -> float:
    """Map persisted native tracking CFO to trajectory/export units."""
    scale = CANONICAL_RF_HZ / actual_rf_hz
    return scale * (native_tracking_cfo_hz - relative_alias_index * ALIAS_SPACING_HZ)
