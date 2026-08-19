"""Release-local execution contract and adapter for WP11 calibration extraction."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Literal, Self, cast

from pydantic import model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest, sha256_digest
from leo.contracts.scientific import TrustedNativeReleaseEvidenceV2
from leo.pipeline import IqReader
from leo.qualification.frequency_calibration import (
    CalibrationCaptureEnvelopeV1,
    CalibrationExtractorReceiptV1,
    FrequencyCalibrationPlanV1,
)
from leo.qualification.frequency_calibration_extractor import ExactWindowIqReader
from leo.qualification.native_execution import (
    _MAX_OUTPUT_BYTES,
    _WORKER_ENVIRONMENT,
    _WORKER_ENVIRONMENT_DIGEST,
    ReleaseLocalNativeEvidenceExecutor,
    _snapshot_receiver,
    _temporary_file_at,
)
from leo.qualification.native_release import _open_absolute_directory


class ReleaseLocalCalibrationExtractionV1(ContractModel):
    schema_version: Literal[1] = 1
    execution_digest: Sha256Digest
    release: TrustedNativeReleaseEvidenceV2
    execution_environment_digest: Sha256Digest
    worker_output_digest: Sha256Digest
    iq_snapshot_digest: Sha256Digest
    plan_digest: Sha256Digest
    capture_envelope_digest: Sha256Digest
    extraction: CalibrationExtractorReceiptV1

    @model_validator(mode="after")
    def _bound(self) -> Self:
        if (
            self.execution_environment_digest != _WORKER_ENVIRONMENT_DIGEST
            or self.capture_envelope_digest != self.extraction.envelope_digest
            or self.extraction.git_revision != self.release.source_revision
            or self.extraction.source_tree_digest != self.release.source_tree_digest
            or self.extraction.executable_digest != self.release.release_metadata_digest
        ):
            raise ValueError("release-local calibration execution binding is invalid")
        if self.execution_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"execution_digest"})
        ):
            raise ValueError("release-local calibration execution digest does not match")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        values = {"schema_version": 1, **values}
        digest_values = {
            key: value.model_dump(mode="json") if isinstance(value, ContractModel) else value
            for key, value in values.items()
        }
        return cls.model_validate(
            {**values, "execution_digest": canonical_digest(digest_values)}
        )


class ReleaseLocalCalibrationExtractor:
    """Run the frozen calibration extractor only inside the validated release."""

    def __init__(self, *, scratch_root: Path = Path("/var/tmp")) -> None:
        # Reuse the reviewed confinement constructor, then retain only its root.
        ReleaseLocalNativeEvidenceExecutor(scratch_root=scratch_root)
        self._scratch_root = scratch_root

    def execute(
        self,
        *,
        plan: FrequencyCalibrationPlanV1,
        capture: CalibrationCaptureEnvelopeV1,
        reader: ExactWindowIqReader,
        release: TrustedNativeReleaseEvidenceV2,
    ) -> ReleaseLocalCalibrationExtractionV1:
        release_root = Path(release.release_path)
        worker = release_root / "tools/native_evidence_worker.py"
        interpreter = release_root / ".venv/bin/python"
        ReleaseLocalNativeEvidenceExecutor._verify_executables(worker, interpreter, release)
        scratch_fd = _open_absolute_directory(self._scratch_root)
        try:
            with _temporary_file_at(scratch_fd) as snapshot:
                iq_digest = _snapshot_receiver(
                    snapshot.fileno(),
                    iq=cast(IqReader, reader),
                    receiver_id=1,
                    block_samples=1_000_000,
                )
                with (
                    _temporary_file_at(scratch_fd) as output,
                    _temporary_file_at(scratch_fd) as errors,
                ):
                    subprocess.run(
                        (
                            str(interpreter),
                            "-I",
                            str(worker),
                            "--mode",
                            "calibration",
                            "--iq-fd",
                            str(snapshot.fileno()),
                            "--iq-sha256",
                            iq_digest,
                            "--plan-json",
                            plan.model_dump_json(),
                            "--capture-json",
                            capture.model_dump_json(),
                        ),
                        cwd=release_root,
                        env=_WORKER_ENVIRONMENT,
                        stdin=subprocess.DEVNULL,
                        stdout=output,
                        stderr=errors,
                        pass_fds=(snapshot.fileno(),),
                        timeout=6 * 60 * 60,
                        check=True,
                    )
                    output.seek(0)
                    stdout = output.read(_MAX_OUTPUT_BYTES + 1)
        finally:
            os.close(scratch_fd)
        if len(stdout) > _MAX_OUTPUT_BYTES:
            raise ValueError("calibration worker output exceeded its bound")
        ReleaseLocalNativeEvidenceExecutor._verify_executables(worker, interpreter, release)
        payload = json.loads(stdout)
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != 1
            or payload.get("mode") != "calibration"
            or payload.get("iq_sha256") != iq_digest
            or payload.get("plan_digest") != plan.plan_digest
            or payload.get("capture_envelope_digest") != capture.envelope_digest
            or payload.get("runtime_package_tree_digest")
            != release.runtime_package_tree_digest
        ):
            raise ValueError("calibration worker output binding is invalid")
        extraction = CalibrationExtractorReceiptV1.model_validate(payload.get("extraction"))
        if extraction.envelope_digest != capture.envelope_digest:
            raise ValueError("calibration worker extraction is bound to another capture")
        return ReleaseLocalCalibrationExtractionV1.create(
            release=release,
            execution_environment_digest=_WORKER_ENVIRONMENT_DIGEST,
            worker_output_digest=sha256_digest(stdout),
            iq_snapshot_digest=iq_digest,
            plan_digest=plan.plan_digest,
            capture_envelope_digest=capture.envelope_digest,
            extraction=extraction,
        )
