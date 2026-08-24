"""Canonical scanner interpretation of the Pluto IIO metadata word."""

RX_OVERFLOW_METADATA_FLAG = 1 << 11


def metadata_reports_rx_overflow(metadata_flags: int) -> bool:
    """Return the FPGA/IIO RX-overflow state encoded in metadata bit 11."""

    if not isinstance(metadata_flags, int) or isinstance(metadata_flags, bool):
        raise TypeError("scanner metadata flags must be one integer")
    if metadata_flags < 0:
        raise ValueError("scanner metadata flags cannot be negative")
    return bool(metadata_flags & RX_OVERFLOW_METADATA_FLAG)
