from datetime import UTC, datetime

import pytest

from leo.contracts.scanner_tracking import ScannerTrackingProductV1
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
