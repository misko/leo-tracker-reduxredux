from __future__ import annotations

from pathlib import Path

import pytest

from leo.analysis.starlink import (
    SymbolwiseAcquisitionConfig,
    native_acquisition_configuration_digest,
    native_qam_configuration_digest,
    native_template_digest,
)
from leo.contracts import (
    CalibrationEvidenceV1,
    DetectorPipelineBindingV1,
    MatchedPilotAcceptanceConfigV1,
    ReceiverFrequencyCalibrationV1,
    ReceiverPathIdentityV1,
    TrustedNativeReleaseEvidenceV2,
    canonical_digest,
)
from leo.qualification.native_execution import (
    ReleaseLocalNativeEvidenceExecutor,
    _expected_window_iq_digests,
)
from leo.qualification.native_release import _file_digest


def _fixture(tmp_path: Path):
    revision = "a" * 40
    release = tmp_path / "deployment/releases" / revision
    worker = release / "tools/native_evidence_worker.py"
    interpreter = release / ".venv/bin/python"
    worker.parent.mkdir(parents=True)
    interpreter.parent.mkdir(parents=True)
    worker.write_text("# reviewed worker\n")
    interpreter.write_text("#!/bin/sh\n")
    values = {
        "schema_version": 2,
        "kind": "validated-current-native-release",
        "pipeline_release": "sealed-release",
        "source_revision": revision,
        "git_tree": "b" * 40,
        "source_tree_digest": "sha256:" + "1" * 64,
        "release_metadata_digest": "sha256:" + "2" * 64,
        "worker_digest": _file_digest(worker),
        "interpreter_digest": _file_digest(interpreter),
        "release_path": str(release),
        "validator": "deployed-release-validators-v1",
    }
    evidence = TrustedNativeReleaseEvidenceV2(
        **values,
        evidence_digest=canonical_digest(values),
    )
    binding = DetectorPipelineBindingV1.create(
        native_source_revision=revision,
        native_source_tree_digest=evidence.source_tree_digest,
        native_release_manifest_digest=evidence.release_metadata_digest,
        native_template_digest=native_template_digest(),
        native_acquisition_configuration_digest=native_acquisition_configuration_digest(
            SymbolwiseAcquisitionConfig(maximum_probe_samples=25_000)
        ),
        native_qam_configuration_digest=native_qam_configuration_digest(),
        pipeline_release=evidence.pipeline_release,
    )
    path = ReceiverPathIdentityV1(
        radio_id="radio-a",
        radio_serial="serial-a",
        receiver_id=1,
        physical_receiver_id="radio-a-rx1",
        capture_utc_ns=1,
        capture_end_utc_ns=60_000_000_001,
        hardware_epoch_id="epoch-a",
        session_id="session-a",
        stream_id="stream-a",
        manifest_digest="sha256:" + "3" * 64,
        profile_revision_digest="sha256:" + "4" * 64,
    )
    calibration = ReceiverFrequencyCalibrationV1.create(
        calibration_id="cal-a",
        radio_id=path.radio_id,
        radio_serial=path.radio_serial,
        receiver_id=1,
        physical_receiver_id=path.physical_receiver_id,
        hardware_epoch_id=path.hardware_epoch_id,
        center_hz=0,
        uncertainty_lower_hz=-1,
        uncertainty_upper_hz=1,
        valid_from_utc_ns=0,
        valid_until_utc_ns=100_000_000_000,
        method="fixture",
        created_utc_ns=0,
        evidence=(
            CalibrationEvidenceV1(
                kind="fixture",
                uri="fixture://cal-a",
                digest="sha256:" + "5" * 64,
            ),
        ),
    )
    return (
        evidence,
        worker,
        interpreter,
        MatchedPilotAcceptanceConfigV1.create(detector_binding=binding),
        path,
        calibration,
    )


class _NeverReadIq:
    sample_rate_hz = 2_500_000
    sample_count = 150_000_000
    center_frequency_hz = 1
    receiver_ids = (1,)

    def iter_blocks(self, *, block_samples):
        raise AssertionError(f"IQ must not be read after stale worker detection: {block_samples}")


@pytest.mark.parametrize("scratch", (Path("/mnt/qnap01"), Path("/mnt/qnap01/science")))
def test_release_executor_rejects_qnap_scratch_without_access(scratch: Path) -> None:
    with pytest.raises(ValueError, match="local storage"):
        ReleaseLocalNativeEvidenceExecutor(scratch_root=scratch)


def test_release_executor_rejects_symlinked_scratch_before_following_qnap(
    tmp_path: Path,
) -> None:
    scratch = tmp_path / "scratch-alias"
    scratch.symlink_to("/mnt/qnap01/must-not-open")
    with pytest.raises(ValueError, match="symlink"):
        ReleaseLocalNativeEvidenceExecutor(scratch_root=scratch)


def test_release_executor_requires_precreated_scratch(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inaccessible"):
        ReleaseLocalNativeEvidenceExecutor(scratch_root=tmp_path / "absent")


def test_expected_window_digests_bind_each_exact_scheduled_window(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.ci16"
    descriptor = snapshot.open("w+b")
    try:
        descriptor.truncate(150_000_000 * 4)
        baseline = _expected_window_iq_digests(descriptor.fileno())
        descriptor.seek(250_000 * 4)
        descriptor.write(b"\x01\x00\x00\x00")
        descriptor.flush()
        mutated = _expected_window_iq_digests(descriptor.fileno())
    finally:
        descriptor.close()
    assert len(baseline) == 600
    assert mutated[0] == baseline[0]
    assert mutated[1] != baseline[1]
    assert mutated[2:] == baseline[2:]


@pytest.mark.parametrize("target", ("worker", "interpreter"))
def test_release_executor_rejects_stale_executable_before_iq_access(
    tmp_path: Path,
    target: str,
) -> None:
    evidence, worker, interpreter, config, path, calibration = _fixture(tmp_path)
    (worker if target == "worker" else interpreter).write_text("tampered\n")
    executor = ReleaseLocalNativeEvidenceExecutor(scratch_root=tmp_path)
    with pytest.raises(ValueError, match="changed"):
        executor.execute(
            iq=_NeverReadIq(),
            path_identity=path,
            calibration=calibration,
            release=evidence,
            config=config,
        )
