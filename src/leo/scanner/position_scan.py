"""Configuration for the additive v6 position acquisition policy."""

from __future__ import annotations

from dataclasses import dataclass

from leo.scanner.continuous_window import ContinuousWindowConfiguration
from leo.scanner.short_window import RfMappingAuthority, ShortWindowConfiguration, ShortWindowTarget


@dataclass(frozen=True, slots=True)
class PositionScanConfiguration(ContinuousWindowConfiguration):
    sample_rate_hz: int = 10_000_000
    policy_id: str = "ordered-position-24-20ms-v1"

    def __post_init__(self) -> None:
        if (
            len(self.targets) != 24
            or self.receiver_ids != (0, 1)
            or self.sample_rate_hz != 10_000_000
            or self.window_ms != 20
            or self.transition_budget_ms != 20
            or self.policy_id != "ordered-position-24-20ms-v1"
        ):
            raise ValueError("position scan requires 24 targets, dual RX, 10 MS/s and 20 ms")
        if len({target.target_id for target in self.targets}) != 24:
            raise ValueError("position scan target identities must be unique")
        baseline = ContinuousWindowConfiguration(
            targets=self.targets[:8],
            receiver_ids=self.receiver_ids,
            gain_db=self.gain_db,
            threshold_dbfs=self.threshold_dbfs,
            transition_budget_ms=self.transition_budget_ms,
            sample_rate_hz=self.sample_rate_hz,
            window_ms=self.window_ms,
            threshold_policy_id=self.threshold_policy_id,
            calibration_id=self.calibration_id,
            segment_windows=self.segment_windows,
            chunk_windows=self.chunk_windows,
            reserve_bytes=self.reserve_bytes,
        )
        object.__setattr__(self, "reserve_bytes", baseline.reserve_bytes)
        object.__setattr__(self, "threshold_policy_id", baseline.threshold_policy_id)

    def power_configuration(self) -> ShortWindowConfiguration:
        return ShortWindowConfiguration(
            targets=self.targets[:8],
            receiver_ids=self.receiver_ids,
            physical_receiver_labels=("RX1", "RX2"),
            gain_db=self.gain_db,
            threshold_dbfs=self.threshold_dbfs,
            transition_budget_ms=self.transition_budget_ms,
            threshold_policy_id=self.threshold_policy_id,
            calibration_id=self.calibration_id,
        )


def position_targets() -> tuple[ShortWindowTarget, ...]:
    bases = (
        1_081_328_125,
        1_331_328_125,
        1_581_328_125,
        1_831_328_125,
        1_231_328_125,
        1_481_328_125,
        1_731_328_125,
        1_981_328_125,
    )
    return tuple(
        ShortWindowTarget(
            target_id=f"ch{channel}-{axis}",
            if_center_hz=base + offset,
            channel=channel,
            lnb_lo_hz=9_750_000_000 if channel <= 4 else 10_600_000_000,
            rf_center_hz=base + offset + (9_750_000_000 if channel <= 4 else 10_600_000_000),
            rf_mapping_authority=RfMappingAuthority.HYPOTHESIS,
            profile_id="position-high34-layout24-v1",
        )
        for channel, base in enumerate(bases, 1)
        for axis, offset in zip("XYZ", (0, 15_000_000, 30_000_000), strict=True)
    )
