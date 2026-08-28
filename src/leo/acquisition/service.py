"""Small application service suitable for CLI ``once`` and later continuous loops."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from threading import Event
from uuid import uuid4

from leo.acquisition.coordinator import AcquisitionCoordinator
from leo.acquisition.models import AdmissionEstimate, CaptureSessionResult
from leo.contracts.mixed_rate_capture import CapturePlanV3, CapturePlanV4
from leo.contracts.profile import CapturePlanV1
from leo.contracts.radio import RadioSettingsV1
from leo.radio.ports import RadioSource


class AcquisitionApplication:
    def __init__(self, coordinator: AcquisitionCoordinator) -> None:
        self.coordinator = coordinator

    def estimate(self, plan: CapturePlanV1 | CapturePlanV3 | CapturePlanV4) -> AdmissionEstimate:
        return self.coordinator.estimate_admission(plan)

    def once(
        self,
        plan: CapturePlanV1 | CapturePlanV3 | CapturePlanV4,
        sources: Mapping[str, RadioSource],
        *,
        session_id: str | None = None,
        cancel: Event | None = None,
        extra_tags: tuple[str, ...] = (),
        requested_settings_by_radio: Mapping[str, RadioSettingsV1] | None = None,
    ) -> CaptureSessionResult:
        return self.coordinator.capture_once(
            plan,
            sources,
            session_id=session_id or self.new_session_id(),
            cancel=cancel,
            extra_tags=extra_tags,
            requested_settings_by_radio=requested_settings_by_radio,
        )

    def new_session_id(self) -> str:
        created = datetime.fromtimestamp(
            self.coordinator.clock.utc_ns() / 1_000_000_000,
            tz=UTC,
        )
        return f"cap-{created:%Y%m%dT%H%M%S}-{uuid4().hex[:12]}"
