from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from leo.contracts.digests import sha256_digest
from leo.contracts.radio import RadioIdentityV1, RadioSettingsV1, ReceiverGainV1
from leo.contracts.states import GainMode, RadioTransport, StarlinkEdge
from leo.scanner.models import ScannerConfiguration, ScanTarget
from leo.scanner.replay import (
    PreparedScannerReplayFrame,
    ScannerReferenceLabel,
    ScannerReplayDatasetRecipeV1,
    ScannerReplayFrameRecipeV1,
    ScannerReplayLabelEvidenceV1,
    ScannerReplaySourceV1,
    ScannerReplaySplit,
    ScannerReplaySweepRecipeV1,
    prepare_scanner_replay_dataset,
)
from leo.storage import (
    BundleCorruptionError,
    RecordingScannerReplaySource,
    ScannerReplayStore,
    replay_scanner_analysis_source,
)

_DIGEST = "sha256:" + "1" * 64


def _configuration() -> ScannerConfiguration:
    return ScannerConfiguration(
        lnb_lo_hz=9_000,
        sample_rate_hz=1_000,
        bandwidth_hz=1_000,
        dwell_ms=20,
        receiver_ids=(0, 1),
        targets=(
            ScanTarget(
                channel=1,
                edge=StarlinkEdge.LOWER,
                rf_center_hz=10_000,
                if_center_hz=1_000,
            ),
            ScanTarget(
                channel=1,
                edge=StarlinkEdge.UPPER,
                rf_center_hz=11_000,
                if_center_hz=2_000,
            ),
        ),
    )


def _evidence(index: int) -> ScannerReplayLabelEvidenceV1:
    return ScannerReplayLabelEvidenceV1(
        method="glrt64-reviewed-v1",
        digest=f"sha256:{index + 1:064x}",
        uri=f"bulk://analysis/source-{index}",
    )


def _recipe() -> ScannerReplayDatasetRecipeV1:
    frames = tuple(
        ScannerReplayFrameRecipeV1(
            target_index=index,
            source_session_id=f"source-{index}",
            source_stream_id="stream-a",
            source_sample_start=10 + index,
            label=(ScannerReferenceLabel.ACTIVE if index == 0 else ScannerReferenceLabel.QUIET),
            evidence=_evidence(index),
        )
        for index in range(2)
    )
    return ScannerReplayDatasetRecipeV1(
        dataset_id="dataset-a",
        generator_id="scanner-replay-test-v1",
        configuration=_configuration(),
        sweeps=(
            ScannerReplaySweepRecipeV1(
                sweep_id="sweep-a",
                split=ScannerReplaySplit.TEST,
                frames=frames,
            ),
        ),
    )


def _settings(center_frequency_hz: int) -> RadioSettingsV1:
    return RadioSettingsV1(
        center_frequency_hz=center_frequency_hz,
        sample_rate_hz=1_000,
        bandwidth_hz=1_000,
        receiver_ids=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30.0),
            ReceiverGainV1(receiver_id=1, gain_db=30.0),
        ),
    )


class _Source:
    def read_frame(self, recipe, target, configuration):
        index = recipe.target_index
        positions = np.arange(configuration.dwell_samples, dtype=np.int16) + index * 100
        samples = np.empty((configuration.dwell_samples, 2, 2), dtype="<i2")
        samples[:, 0, 0] = positions
        samples[:, 0, 1] = positions + 1
        samples[:, 1, 0] = positions + 2
        samples[:, 1, 1] = positions + 3
        source = ScannerReplaySourceV1(
            session_id=recipe.source_session_id,
            recording_uri=f"bulk://recordings/2026/08/21/{recipe.source_session_id}",
            recording_manifest_sha256=f"sha256:{index + 10:064x}",
            stream_id=recipe.source_stream_id,
            radio_id=f"radio-{index}",
            radio_serial=f"serial-{index}",
            source_receiver_ids=(0, 1),
            source_sample_start=recipe.source_sample_start,
            source_sample_count=configuration.dwell_samples,
            requested_settings=_settings(target.if_center_hz),
            applied_settings=_settings(target.if_center_hz - 2),
        )
        return PreparedScannerReplayFrame(recipe=recipe, source=source, samples=samples)


def test_replay_dataset_materializes_pr5_compatible_framed_ci16_without_label_leakage(
    tmp_path,
) -> None:
    recipe = _recipe()
    prepared = prepare_scanner_replay_dataset(recipe, _Source())
    store = ScannerReplayStore(tmp_path / "bulk")

    dataset = store.publish(prepared)
    sweep = store.inspect_sweep(dataset.dataset_id, "sweep-a")
    values = store.read_ci16(sweep)

    assert sorted(path.name for path in sweep.path.iterdir()) == [
        "iq.ci16.zst",
        "manifest.json",
    ]
    assert values.shape == (40, 2, 2)
    assert values.dtype == np.dtype("<i2")
    assert not values.flags.writeable
    assert values[0].tolist() == [[0, 1], [2, 3]]
    assert values[20].tolist() == [[100, 101], [102, 103]]
    assert [(frame.sample_start, frame.sample_count) for frame in sweep.manifest.frames] == [
        (0, 20),
        (20, 20),
    ]
    assert sweep.manifest.frames[0].source.requested_settings.center_frequency_hz == 1_000
    assert sweep.manifest.frames[0].source.applied_settings.center_frequency_hz == 998
    document = json.loads((sweep.path / "manifest.json").read_bytes())
    assert document["sample_format"] == "ci16_le"
    assert document["sample_layout"] == "sample_receiver_iq"
    assert "label" not in json.dumps(document)
    assert "host_request_utc_ns_lower" not in json.dumps(document)
    assert [item.label for item in dataset.truth.items] == [
        ScannerReferenceLabel.ACTIVE,
        ScannerReferenceLabel.QUIET,
    ]
    assert (dataset.path / "truth.v1.json").parent != sweep.path

    source = replay_scanner_analysis_source(store, sweep)
    assert source.input_manifest_sha256 == sweep.manifest_sha256
    assert [item.source_sample_start for item in source.frames] == [0, 20]
    assert source.frames[0].requested_if_center_hz == 1_000
    assert source.frames[0].actual_if_center_hz == 998


def test_replay_dataset_materialization_is_byte_deterministic(tmp_path) -> None:
    prepared = prepare_scanner_replay_dataset(_recipe(), _Source())
    first = ScannerReplayStore(tmp_path / "first").publish(prepared)
    second = ScannerReplayStore(tmp_path / "second").publish(prepared)

    first_files = {
        path.relative_to(first.path): path.read_bytes()
        for path in first.path.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second.path): path.read_bytes()
        for path in second.path.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files


def test_replay_recipe_rejects_source_session_split_leakage() -> None:
    recipe = _recipe()
    repeated = tuple(
        frame.model_copy(update={"source_session_id": "shared-session"})
        for frame in recipe.sweeps[0].frames
    )
    validation = recipe.sweeps[0].model_copy(
        update={"sweep_id": "sweep-validation", "split": ScannerReplaySplit.VALIDATION}
    )

    with pytest.raises(ValidationError, match="cannot cross dataset splits"):
        ScannerReplayDatasetRecipeV1.model_validate(
            {
                **recipe.model_dump(),
                "sweeps": (
                    recipe.sweeps[0].model_copy(update={"frames": repeated}),
                    validation.model_copy(update={"frames": repeated}),
                ),
            }
        )


def test_replay_reader_rejects_payload_corruption(tmp_path) -> None:
    store = ScannerReplayStore(tmp_path / "bulk")
    dataset = store.publish(prepare_scanner_replay_dataset(_recipe(), _Source()))
    sweep = store.inspect_sweep(dataset.dataset_id, "sweep-a")
    payload_path = sweep.path / "iq.ci16.zst"
    payload = bytearray(payload_path.read_bytes())
    payload[len(payload) // 2] ^= 0x80
    payload_path.write_bytes(payload)

    with pytest.raises(BundleCorruptionError, match="compressed digest mismatch"):
        store.read_ci16(sweep)


def test_recording_source_adapter_reads_verified_native_ci16_slice() -> None:
    configuration = _configuration()
    frame_recipe = _recipe().sweeps[0].frames[0]
    expected = np.arange(80, dtype=np.int16).reshape(20, 2, 2)
    radio = RadioIdentityV1(
        radio_id="radio-a",
        serial="serial-a",
        uri="ip:192.0.2.1",
        transport=RadioTransport.IIO_IP,
    )
    stream = SimpleNamespace(
        stream_id="stream-a",
        requested_settings=_settings(1_000),
        applied_settings=_settings(1_000),
        radio=radio,
    )
    bundle = SimpleNamespace(
        session_id="source-0",
        uri="bulk://recordings/2026/08/21/source-0",
        manifest_sha256=_DIGEST,
        manifest=SimpleNamespace(streams=(stream,)),
    )

    class _Recordings:
        def inspect(self, session_id):
            assert session_id == "source-0"
            return bundle

        def read_ci16(
            self,
            inspected,
            stream_id,
            sample_start,
            sample_count,
            *,
            receiver_ids,
            verify,
        ):
            assert inspected is bundle
            assert (stream_id, sample_start, sample_count) == ("stream-a", 10, 20)
            assert receiver_ids == (0, 1)
            assert verify is True
            return expected.copy()

    adapter = RecordingScannerReplaySource(_Recordings())  # type: ignore[arg-type]
    prepared = adapter.read_frame(frame_recipe, configuration.targets[0], configuration)

    np.testing.assert_array_equal(prepared.samples, expected)
    assert prepared.source.recording_manifest_sha256 == _DIGEST
    assert sha256_digest(prepared.samples.tobytes()) == sha256_digest(expected.tobytes())
