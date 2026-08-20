"""Bounded random paired-radio Starlink channel selection."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from leo.contracts.profile import CaptureProfileV1
from leo.contracts.radio import RadioSettingsV1
from leo.contracts.states import GainMode, StarlinkEdge

RandBelow = Callable[[int], int]

# Complete Qin/Starlink Ku downlink channel authority. Live acquisition remains
# deliberately bounded to the separately named capture subset until channels
# 5-8 are enabled against the supported RF hardware.
SUPPORTED_STARLINK_CHANNELS = tuple(range(1, 9))
CAPTURE_STARLINK_CHANNELS = tuple(range(1, 5))
STARLINK_LNB_LO_HZ = 9_750_000_000
STARLINK_CHANNEL_SPACING_HZ = 250_000_000
_FIRST_LOWER_EDGE_RF_CENTER_HZ = 10_709_687_500
_FIRST_UPPER_EDGE_RF_CENTER_HZ = 10_940_312_500


class PairedTuningBranch(StrEnum):
    SAME = "same"
    SAME_CHANNEL_OPPOSITE_EDGE = "same_channel_opposite_edge"
    INDEPENDENT = "independent"


@dataclass(frozen=True, slots=True)
class StarlinkTuning:
    channel: int
    edge: StarlinkEdge
    center_frequency_hz: int


@dataclass(frozen=True, slots=True)
class PairedStarlinkTuning:
    branch: PairedTuningBranch
    radio_gain_modes: tuple[tuple[str, GainMode], tuple[str, GainMode]]
    radio_tunings: tuple[tuple[str, StarlinkTuning], tuple[str, StarlinkTuning]]

    @property
    def manifest_tags(self) -> tuple[str, ...]:
        tags = [f"tuning_policy:{self.branch.value}"]
        tags.extend(
            f"gain_mode:stream-{index}:{gain_mode.value}"
            for index, (_, gain_mode) in enumerate(self.radio_gain_modes)
        )
        tags.extend(
            f"tuning:stream-{index}:ch{tuning.channel}:{tuning.edge.value}"
            for index, (_, tuning) in enumerate(self.radio_tunings)
        )
        return tuple(sorted(tags))

    def requested_settings(self, profile: CaptureProfileV1) -> dict[str, RadioSettingsV1]:
        gain_modes = dict(self.radio_gain_modes)
        return {
            radio_id: RadioSettingsV1(
                center_frequency_hz=tuning.center_frequency_hz,
                sample_rate_hz=profile.sample_rate_hz,
                bandwidth_hz=profile.bandwidth_hz,
                receiver_ids=profile.receivers,
                gain_mode=gain_modes[radio_id],
                gains=profile.gains if gain_modes[radio_id] is GainMode.MANUAL else (),
            )
            for radio_id, tuning in self.radio_tunings
        }


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


def sample_paired_starlink_tuning(
    radio_ids: tuple[str, str],
    *,
    randbelow: RandBelow = secrets.randbelow,
) -> PairedStarlinkTuning:
    """Draw paired tuning plus independent manual/slow-attack gain modes."""

    gain_modes = tuple(_draw_gain_mode(randbelow) for _ in radio_ids)
    branch_draw = randbelow(4)
    if branch_draw == 0:
        first = _draw_tuning(randbelow)
        second = first
        branch = PairedTuningBranch.SAME
    elif branch_draw == 1:
        channel = _draw_channel(randbelow)
        first_edge = _draw_edge(randbelow)
        first = _tuning(channel, first_edge)
        second = _tuning(channel, _opposite(first_edge))
        branch = PairedTuningBranch.SAME_CHANNEL_OPPOSITE_EDGE
    else:
        first = _draw_tuning(randbelow)
        second = _draw_tuning(randbelow)
        branch = PairedTuningBranch.INDEPENDENT
    return PairedStarlinkTuning(
        branch=branch,
        radio_gain_modes=(
            (radio_ids[0], gain_modes[0]),
            (radio_ids[1], gain_modes[1]),
        ),
        radio_tunings=((radio_ids[0], first), (radio_ids[1], second)),
    )


def _draw_tuning(randbelow: RandBelow) -> StarlinkTuning:
    return _tuning(_draw_channel(randbelow), _draw_edge(randbelow))


def _draw_channel(randbelow: RandBelow) -> int:
    return CAPTURE_STARLINK_CHANNELS[randbelow(len(CAPTURE_STARLINK_CHANNELS))]


def _draw_edge(randbelow: RandBelow) -> StarlinkEdge:
    return StarlinkEdge.LOWER if randbelow(2) == 0 else StarlinkEdge.UPPER


def _draw_gain_mode(randbelow: RandBelow) -> GainMode:
    return GainMode.SLOW_ATTACK if randbelow(2) == 0 else GainMode.MANUAL


def _tuning(channel: int, edge: StarlinkEdge) -> StarlinkTuning:
    return StarlinkTuning(
        channel=channel,
        edge=edge,
        center_frequency_hz=starlink_edge_if_center_frequency_hz(channel, edge),
    )


def _validate_channel(channel: int) -> None:
    if isinstance(channel, bool) or not isinstance(channel, int):
        raise TypeError("Starlink channel must be an integer")
    if channel not in SUPPORTED_STARLINK_CHANNELS:
        raise ValueError(
            f"Starlink channel must be one of {SUPPORTED_STARLINK_CHANNELS}; got {channel}"
        )


def _opposite(edge: StarlinkEdge) -> StarlinkEdge:
    return StarlinkEdge.UPPER if edge is StarlinkEdge.LOWER else StarlinkEdge.LOWER
