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

_LOWER_IF_CENTER_HZ = {
    1: 959_687_500,
    2: 1_209_687_500,
    3: 1_459_687_500,
    4: 1_709_687_500,
}
_UPPER_IF_CENTER_HZ = {
    1: 1_190_312_500,
    2: 1_440_312_500,
    3: 1_690_312_500,
    4: 1_940_312_500,
}


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
    gain_mode: GainMode
    radio_tunings: tuple[tuple[str, StarlinkTuning], tuple[str, StarlinkTuning]]

    @property
    def manifest_tags(self) -> tuple[str, ...]:
        tags = [f"gain_mode:{self.gain_mode.value}", f"tuning_policy:{self.branch.value}"]
        tags.extend(
            f"tuning:stream-{index}:ch{tuning.channel}:{tuning.edge.value}"
            for index, (_, tuning) in enumerate(self.radio_tunings)
        )
        return tuple(sorted(tags))

    def requested_settings(self, profile: CaptureProfileV1) -> dict[str, RadioSettingsV1]:
        return {
            radio_id: RadioSettingsV1(
                center_frequency_hz=tuning.center_frequency_hz,
                sample_rate_hz=profile.sample_rate_hz,
                bandwidth_hz=profile.bandwidth_hz,
                receiver_ids=profile.receivers,
                gain_mode=self.gain_mode,
                gains=profile.gains if self.gain_mode is GainMode.MANUAL else (),
            )
            for radio_id, tuning in self.radio_tunings
        }


def sample_paired_starlink_tuning(
    radio_ids: tuple[str, str],
    *,
    randbelow: RandBelow = secrets.randbelow,
) -> PairedStarlinkTuning:
    """Draw tuning plus one shared 50/50 manual or slow-attack gain mode."""

    gain_mode = GainMode.SLOW_ATTACK if randbelow(2) == 0 else GainMode.MANUAL
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
        gain_mode=gain_mode,
        radio_tunings=((radio_ids[0], first), (radio_ids[1], second)),
    )


def _draw_tuning(randbelow: RandBelow) -> StarlinkTuning:
    return _tuning(_draw_channel(randbelow), _draw_edge(randbelow))


def _draw_channel(randbelow: RandBelow) -> int:
    return randbelow(4) + 1


def _draw_edge(randbelow: RandBelow) -> StarlinkEdge:
    return StarlinkEdge.LOWER if randbelow(2) == 0 else StarlinkEdge.UPPER


def _tuning(channel: int, edge: StarlinkEdge) -> StarlinkTuning:
    centers = _LOWER_IF_CENTER_HZ if edge is StarlinkEdge.LOWER else _UPPER_IF_CENTER_HZ
    return StarlinkTuning(channel=channel, edge=edge, center_frequency_hz=centers[channel])


def _opposite(edge: StarlinkEdge) -> StarlinkEdge:
    return StarlinkEdge.UPPER if edge is StarlinkEdge.LOWER else StarlinkEdge.LOWER
