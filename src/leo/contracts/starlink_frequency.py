"""Canonical Starlink channel, pilot, and maximum-coverage IF geometry."""

from __future__ import annotations

from leo.contracts.states import StarlinkEdge

SUPPORTED_STARLINK_CHANNELS = tuple(range(1, 9))
STARLINK_LNB_LO_HZ = 9_750_000_000
STARLINK_CHANNEL_SPACING_HZ = 250_000_000
STARLINK_CHANNEL_OCCUPIED_BANDWIDTH_HZ = 240_000_000
_FIRST_LOWER_EDGE_RF_CENTER_HZ = 10_709_687_500
_FIRST_UPPER_EDGE_RF_CENTER_HZ = 10_940_312_500


def starlink_edge_rf_center_frequency_hz(
    channel: int,
    edge: StarlinkEdge | str,
) -> int:
    """Return the RF center of one published eight-tone edge-pilot band."""

    _validate_channel(channel)
    selected_edge = StarlinkEdge(edge)
    first_hz = (
        _FIRST_LOWER_EDGE_RF_CENTER_HZ
        if selected_edge is StarlinkEdge.LOWER
        else _FIRST_UPPER_EDGE_RF_CENTER_HZ
    )
    return first_hz + (channel - 1) * STARLINK_CHANNEL_SPACING_HZ


def starlink_edge_if_center_frequency_hz(
    channel: int,
    edge: StarlinkEdge | str,
) -> int:
    """Return the IF center after the repository's documented 9.75 GHz LO."""

    return starlink_edge_rf_center_frequency_hz(channel, edge) - STARLINK_LNB_LO_HZ


def starlink_channel_if_bounds_hz(channel: int) -> tuple[int, int]:
    """Return the published 240 MHz occupied channel bounds after LNB conversion."""

    _validate_channel(channel)
    lower_pilot = starlink_edge_if_center_frequency_hz(channel, StarlinkEdge.LOWER)
    upper_pilot = starlink_edge_if_center_frequency_hz(channel, StarlinkEdge.UPPER)
    midpoint = (lower_pilot + upper_pilot) // 2
    half_width = STARLINK_CHANNEL_OCCUPIED_BANDWIDTH_HZ // 2
    return midpoint - half_width, midpoint + half_width


def starlink_maximum_coverage_if_center_frequency_hz(
    channel: int,
    edge: StarlinkEdge | str,
    *,
    bandwidth_hz: int,
) -> int:
    """Return the edge-pilot-nearest center whose full passband is in-channel."""

    if isinstance(bandwidth_hz, bool) or not isinstance(bandwidth_hz, int):
        raise TypeError("Starlink capture bandwidth must be an integer")
    if not 0 < bandwidth_hz <= STARLINK_CHANNEL_OCCUPIED_BANDWIDTH_HZ:
        raise ValueError("Starlink capture bandwidth must fit the occupied channel")
    selected_edge = StarlinkEdge(edge)
    pilot_center = starlink_edge_if_center_frequency_hz(channel, selected_edge)
    channel_start, channel_stop = starlink_channel_if_bounds_hz(channel)
    lower_center_limit = channel_start + bandwidth_hz // 2
    upper_center_limit = channel_stop - bandwidth_hz // 2
    return min(max(pilot_center, lower_center_limit), upper_center_limit)


def _validate_channel(channel: int) -> None:
    if isinstance(channel, bool) or not isinstance(channel, int):
        raise TypeError("Starlink channel must be an integer")
    if channel not in SUPPORTED_STARLINK_CHANNELS:
        raise ValueError(
            f"Starlink channel must be one of {SUPPORTED_STARLINK_CHANNELS}; got {channel}"
        )
