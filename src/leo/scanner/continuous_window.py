"""Pure configuration and visit identity for ordered until-STOP acquisition."""

from __future__ import annotations

from dataclasses import dataclass

from leo.scanner.short_window import (
    ShortWindowAcquisition,
    ShortWindowConfiguration,
    ShortWindowTarget,
)


@dataclass(frozen=True, slots=True)
class ContinuousWindowConfiguration:
    targets: tuple[ShortWindowTarget, ...]
    receiver_ids: tuple[int, ...] = (0, 1)
    gain_db: float = 40.0
    threshold_dbfs: float = -38.0
    transition_budget_ms: int = 20
    sample_rate_hz: int = 2_500_000
    window_ms: int = 20
    policy_id: str = "ordered-continuous-20ms-v1"
    threshold_policy_id: str = "mean-component-ci16-minus38-comparison-v1"
    calibration_id: str = "uncalibrated"
    segment_windows: int = 512
    chunk_windows: int = 64
    reserve_bytes: int = 335_544_320

    def __post_init__(self) -> None:
        if len(self.targets) != 8 or self.receiver_ids not in ((0,), (0, 1)):
            raise ValueError(
                "continuous ordered scanning requires eight targets and physical RX1[/RX2]"
            )
        if self.policy_id != "ordered-continuous-20ms-v1":
            raise ValueError("continuous policy identity is immutable")
        if not 1 <= self.chunk_windows <= 256 or not 1 <= self.segment_windows <= 4096:
            raise ValueError("continuous recording segment/chunk bounds are invalid")
        if self.reserve_bytes < self.segment_windows * self.window_bytes:
            raise ValueError("reserve must accommodate a complete uncompressed segment")
        # The existing type validates common geometry/calibration fields only;
        # its finite duration and scheduler are never used for this mode.
        power = self.power_configuration()
        object.__setattr__(self, "threshold_policy_id", power.threshold_policy_id)

    @property
    def window_bytes(self) -> int:
        return 50_000 * len(self.receiver_ids) * 4

    def power_configuration(self) -> ShortWindowConfiguration:
        return ShortWindowConfiguration(
            targets=self.targets,
            receiver_ids=self.receiver_ids,
            physical_receiver_labels=("RX1", "RX2")[: len(self.receiver_ids)],
            gain_db=self.gain_db,
            threshold_dbfs=self.threshold_dbfs,
            transition_budget_ms=self.transition_budget_ms,
            sample_rate_hz=self.sample_rate_hz,
            window_ms=self.window_ms,
            threshold_policy_id=self.threshold_policy_id,
            calibration_id=self.calibration_id,
        )


@dataclass(frozen=True, slots=True)
class ContinuousWindow:
    target: ShortWindowTarget
    acquisition: ShortWindowAcquisition
    session: int
    generation: int
    visit: int
    sweep: int
    target_index: int

    def __post_init__(self) -> None:
        if not 0 <= self.visit < 1 << 64 or self.sweep != self.visit // 8:
            raise ValueError("continuous absolute visit/sweep geometry is invalid")
        if self.target_index != self.visit % 8:
            raise ValueError("continuous window target order is invalid")
        if not 0 < self.session < 1 << 64 or not 0 < self.generation < 1 << 64:
            raise ValueError("continuous run identity is invalid")
        if self.acquisition.generation != self.generation:
            raise ValueError("continuous acquisition generation changed")
