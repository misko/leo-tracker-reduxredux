from __future__ import annotations

from pathlib import Path
from runpy import run_path

import pytest

from leo.application.trusted_matched_recovery import (
    WP11_TRUSTED_MATCHED_STAGE_KEYS,
    PinnedLegacyOracleAuthority,
)
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.scientific import MatchedPilotAcceptanceConfigV1
from leo.pipeline import AnalysisContext, ProductRequirement, PublishedProduct, StageOutcome
from leo.qualification.trusted_matched_recovery_stage import (
    TRUSTED_MATCHED_RECOVERY_PRODUCT,
    TRUSTED_MATCHED_RECOVERY_STAGE,
    TrustedMatchedRecoveryAnalyzer,
    TrustedMatchedRecoveryBinding,
)
from tests.analysis.test_trusted_acceptance_v2 import (
    _binding,
    _calibration,
    _decisions,
    _identity,
    _legacy,
    _native,
)

_LEGACY_HELPERS = run_path(str(Path(__file__).with_name("test_legacy_oracle.py")))
_legacy_receipt = _LEGACY_HELPERS["_receipt"]
_publish_legacy = _LEGACY_HELPERS["_publish"]
_LEGACY_IQ_DIGEST = _LEGACY_HELPERS["IQ_DIGEST"]


class _Iq:
    sample_rate_hz = 2_500_000
    center_frequency_hz = 1_709_521_250
    sample_count = 150_000_000
    receiver_ids = (1,)

    def iter_blocks(self, *, block_samples):
        del block_samples
        return ()


class _Products:
    def __init__(self, document):
        self.document = document

    def read_json(self, requirement: ProductRequirement):
        assert requirement.kind == "starlink.native-known-pilot-evidence"
        assert requirement.accepted_schema_versions == (2,)
        assert requirement.producer_stage_key == "native-known-pilot-evidence"
        assert requirement.required_role is not None
        assert requirement.required_role.value == "scientific"
        assert requirement.required_status is StageOutcome.COMPLETE
        assert requirement.require_available is True
        return self.document


class _Sink:
    def __init__(self) -> None:
        self.document = None

    def publish_json(self, product, document):
        self.document = document
        payload = canonical_json_bytes(document)
        return PublishedProduct(
            product=product,
            logical_uri="bulk://analysis/session/run/trusted.json",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )


class _Binding:
    def __init__(self, value: TrustedMatchedRecoveryBinding) -> None:
        self.value = value

    def resolve(self, _context, _iq, _native):
        return self.value


def test_v2_stage_consumes_same_scope_native_and_remains_nonproduction() -> None:
    identity = _identity()
    binding = _binding()
    config = MatchedPilotAcceptanceConfigV1.create(detector_binding=binding)
    calibration = _calibration(identity)
    legacy = _legacy(identity, calibration, _decisions("legacy_reference"), binding)
    native = _native(
        identity,
        calibration,
        _decisions("native"),
        binding,
        run_id="run-session-a",
    )
    sink = _Sink()
    result = TrustedMatchedRecoveryAnalyzer(
        _Binding(
            TrustedMatchedRecoveryBinding(
                config=config,
                path_identity=identity,
                calibration=calibration,
                legacy_execution=legacy,
            )
        )
    ).analyze(
        AnalysisContext(
            session_id="session-a",
            run_id="run-session-a",
            pipeline_release=binding.pipeline_release,
            scope_key="stream-a",
        ),
        _Iq(),
        _Products(native.model_dump(mode="json")),
        sink,
    )

    assert result.outcome is StageOutcome.COMPLETE
    assert result.products[0].product == TRUSTED_MATCHED_RECOVERY_PRODUCT
    assert result.summary["production_accepted"] is False
    assert sink.document["receipt"]["production_accepted"] is False
    assert TRUSTED_MATCHED_RECOVERY_STAGE.dependencies == (
        "native-known-pilot-evidence",
    )
    assert WP11_TRUSTED_MATCHED_STAGE_KEYS == (
        "native-known-pilot-evidence",
        "trusted-matched-recovery-v2",
    )


def test_v2_stage_rejects_retargeted_native_before_authority() -> None:
    identity = _identity()
    binding = _binding()
    calibration = _calibration(identity)
    native = _native(
        identity,
        calibration,
        _decisions("native"),
        binding,
        run_id="another-run",
    )
    with pytest.raises(ValueError, match="retargeted"):
        TrustedMatchedRecoveryAnalyzer(object()).analyze(  # type: ignore[arg-type]
            AnalysisContext(
                session_id="session-a",
                run_id="run-session-a",
                pipeline_release=binding.pipeline_release,
                scope_key="stream-a",
            ),
            _Iq(),
            _Products(native.model_dump(mode="json")),
            _Sink(),
        )


def test_pinned_legacy_authority_rejects_iq_mismatch_and_symlink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "legacy"
    root.mkdir()
    receipt = _legacy_receipt(tmp_path)
    _publish_legacy(root, "scope.json", receipt)
    authority = PinnedLegacyOracleAuthority(root)
    identity = _identity()
    calibration = _calibration(identity).model_copy(
        update={"center_hz": receipt.config.receiver_center_hz}
    )
    # A hand-mutated calibration cannot cross the contract boundary.
    with pytest.raises(ValueError, match="calibration"):
        authority.resolve(
            receipt_name="scope.json",
            detector_binding=_binding(),
            identity=identity,
            calibration=calibration,
            iq_digest=_LEGACY_IQ_DIGEST,
        )
    valid = type(_calibration(identity)).create(
        calibration_id="legacy-cal",
        radio_id=identity.radio_id,
        radio_serial=identity.radio_serial,
        receiver_id=identity.receiver_id,
        physical_receiver_id=identity.physical_receiver_id,
        hardware_epoch_id=identity.hardware_epoch_id,
        center_hz=receipt.config.receiver_center_hz,
        uncertainty_lower_hz=receipt.config.receiver_center_hz - 1,
        uncertainty_upper_hz=receipt.config.receiver_center_hz + 1,
        valid_from_utc_ns=identity.capture_utc_ns,
        valid_until_utc_ns=identity.capture_end_utc_ns,
        method="fixture",
        created_utc_ns=identity.capture_utc_ns - 1,
        evidence=_calibration(identity).evidence,
    )
    resolved = authority.resolve(
        receipt_name="scope.json",
        detector_binding=_binding(),
        identity=identity,
        calibration=valid,
        iq_digest=_LEGACY_IQ_DIGEST,
    )
    assert resolved.oracle_receipt_digest == receipt.receipt_digest
    assert resolved.session_id == identity.session_id
    assert len(resolved.decisions) == 600
    with pytest.raises(ValueError, match="different IQ"):
        authority.resolve(
            receipt_name="scope.json",
            detector_binding=_binding(),
            identity=identity,
            calibration=valid,
            iq_digest="sha256:" + "0" * 64,
        )
    (root / "linked.json").symlink_to(root / "scope.json")
    with pytest.raises(OSError):
        authority.resolve(
            receipt_name="linked.json",
            detector_binding=_binding(),
            identity=identity,
            calibration=valid,
            iq_digest=_LEGACY_IQ_DIGEST,
        )
