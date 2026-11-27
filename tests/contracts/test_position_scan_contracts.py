import pytest

from leo.contracts.continuous_window import ContinuousRunCheckpointV1
from leo.contracts.digests import canonical_digest
from leo.contracts.position_scan import PositionRunCheckpointV1


def test_new_envelope_admits_24_without_mutating_published_checkpoint():
    fields = dict(
        run_id="position",
        configuration={},
        configuration_sha256=canonical_digest({}),
        host="fixture",
        serial="serial",
        state="running",
        updated_utc_ns=0,
        latest_targets={str(i): {} for i in range(24)},
    )
    new = PositionRunCheckpointV1(**fields)
    assert new.physical_slots == 8 and new.logical_targets == 24
    with pytest.raises(ValueError, match="retention"):
        ContinuousRunCheckpointV1(**fields)
    with pytest.raises(ValueError, match="terminal"):
        PositionRunCheckpointV1(**(fields | {"state": "stopped"}))
