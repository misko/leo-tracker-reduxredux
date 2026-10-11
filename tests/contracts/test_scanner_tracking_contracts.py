from datetime import UTC, datetime

import pytest

from leo.contracts.scanner_tracking import ScannerTrackingProductV1, ScannerTrackingProductV2
from tests.application.test_persistent_hop_tracking import _site
from tests.application.test_scanner_tracking import source


def product():
    s = source()
    return ScannerTrackingProductV1(
        session_id=s.session_id,
        capture_mode=s.capture_mode,
        sample_rate_hz=s.sample_rate_hz,
        input_manifest_sha256=s.input_manifest_sha256,
        analysis_manifest_sha256=s.analysis_manifest_sha256,
        configuration_digest=s.input_manifest_sha256,
        created_at=datetime.now(UTC),
        trajectory_state="unsupported",
        tle_state="pending",
        observer_site=_site(),
    )


@pytest.mark.parametrize(
    "update",
    [
        {"trajectory_state": "complete"},
        {"attempted_group_count": 1},
        {"eligible_group_count": 1},
        {"deferred_group_count": -1},
        {"identity_claimed": True},
    ],
)
def test_publication_rejects_incoherent_accounting_and_identity_claims(update):
    with pytest.raises(ValueError):
        ScannerTrackingProductV1.model_validate({**product().model_dump(), **update})


def test_device_relative_v2_cannot_publish_catalogue_claims():
    legacy = product()
    relative = ScannerTrackingProductV2(
        **legacy.model_dump(exclude={"schema_version", "analysis_id"}),
        trajectory_time_basis="device-counter-relative",
    )
    with pytest.raises(ValueError, match="catalogue authority"):
        ScannerTrackingProductV2.model_validate({**relative.model_dump(), "tle_state": "complete"})


@pytest.mark.parametrize("channel", range(1, 9))
def test_eight_channel_contracts_preserve_legacy_limits(channel):
    from typing import Annotated

    from pydantic import TypeAdapter

    from leo.contracts.scanner_tracking import ScannerTleTrackReviewV2, ScannerTleTrackReviewV3
    from leo.scanner.persistent_hop_tracking import (
        PersistentHopTrajectoryTrackletV1,
        PersistentHopTrajectoryTrackletV2,
    )
    for old, new in ((PersistentHopTrajectoryTrackletV1, PersistentHopTrajectoryTrackletV2),
                     (ScannerTleTrackReviewV2, ScannerTleTrackReviewV3)):
        old_field, new_field = (model.model_fields["channel"] for model in (old, new))
        assert TypeAdapter(Annotated[int, *new_field.metadata]).validate_python(channel) == channel
        if channel > 4:
            with pytest.raises(ValueError):
                TypeAdapter(Annotated[int, *old_field.metadata]).validate_python(channel)
        for invalid in (0, 9):
            with pytest.raises(ValueError):
                TypeAdapter(Annotated[int, *new_field.metadata]).validate_python(invalid)
