import numpy as np
import pytest

from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.radio.fake import FakeRadioSource
from leo.storage.errors import BundleStateError
from leo.storage.staging import RawIqStage


def _block():
    radio = FakeRadioSource("radio-a")
    radio.open()
    radio.configure(
        RadioSettingsV1(
            center_frequency_hz=1_700_000_000,
            sample_rate_hz=20_000_000,
            bandwidth_hz=20_000_000,
            receiver_ids=(0,),
            gain_mode="manual",
            gains=(ReceiverGainV1(receiver_id=0, gain_db=30),),
        )
    )
    return radio.read_block(4)


def test_raw_stage_round_trips_then_removes_only_its_private_files(tmp_path):
    stage = RawIqStage(tmp_path / "stage", maximum_bytes=32)
    block = _block()
    stage.append(block)
    stage.append(block)
    with pytest.raises(BundleStateError, match="before complete"):
        stage.discard_after_finalize()
    stage.seal()
    replay = tuple(stage.blocks())
    assert len(replay) == 2
    assert replay[0].metadata == block.metadata
    np.testing.assert_array_equal(replay[0].samples, block.samples)
    stage.discard_after_finalize()
    assert not (tmp_path / "stage").exists()


def test_raw_stage_enforces_bound_and_detects_corruption(tmp_path):
    stage = RawIqStage(tmp_path / "stage", maximum_bytes=16)
    stage.append(_block())
    with pytest.raises(BundleStateError, match="byte bound"):
        stage.append(_block())
    stage.seal()
    path = tmp_path / "stage" / "iq.ci16"
    payload = path.read_bytes()
    path.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
    with pytest.raises(BundleStateError, match="differs"):
        tuple(stage.blocks())
    assert path.exists()


def test_raw_stage_close_preserves_failure_evidence(tmp_path):
    stage = RawIqStage(tmp_path / "stage", maximum_bytes=16)
    stage.append(_block())
    stage.close()
    assert (tmp_path / "stage" / "iq.ci16").stat().st_size == 16
