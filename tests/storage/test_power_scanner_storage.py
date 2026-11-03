import pytest

from leo.contracts.power_scanner import StandalonePowerCheckpointV1
from leo.storage.continuous_window import run_path
from leo.storage.power_scanner import read_power_checkpoint, write_power_checkpoint


def test_recovery_snapshot_atomic_identity_and_immutable_no_iq(tmp_path):
    path = run_path(tmp_path, "power")
    path.mkdir()
    value = StandalonePowerCheckpointV1(
        run_id="power",
        host="fixture",
        serial="serial",
        session=1,
        generation=2,
        state="recovery_required",
        preparation={"setup": "00"},
        request={"threshold_energy": [1, 1]},
        fault="release unattested",
        updated_utc_ns=0,
    )
    write_power_checkpoint(path, value)
    assert read_power_checkpoint(tmp_path, "power") == value
    assert not list(path.glob("*.partial"))
    changed = value.model_copy(update={"run_id": "foreign"})
    write_power_checkpoint(path, changed)
    with pytest.raises(ValueError, match="identity"):
        read_power_checkpoint(tmp_path, "power")
