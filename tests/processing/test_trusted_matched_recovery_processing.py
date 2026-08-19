from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from leo.analysis.adapters import production_long_dwell_registry
from leo.analysis.graphs import ComputeTier
from leo.analysis.starlink.acceptance import NATIVE_KNOWN_PILOT_EVIDENCE_STAGE
from leo.contracts.scientific import MatchedPilotAcceptanceConfigV1
from leo.pipeline import (
    AnalyzerRegistry,
    ProductRole,
    ProductSpec,
    StageOutcome,
    StageResult,
    StageSpec,
)
from leo.processing import CatalogArtifactProductReader, ProcessingService
from leo.qualification.trusted_matched_recovery_stage import (
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

from .conftest import ProcessingDatabase
from .test_processing_service import _add_release, _execute_until_idle, _prepare_recording


class _Iq:
    sample_rate_hz = 2_500_000
    center_frequency_hz = 1_709_521_250
    sample_count = 150_000_000
    receiver_ids = (1,)

    def iter_blocks(self, *, block_samples):
        del block_samples
        return ()


class _IqProvider:
    def open(self, _execution, _scope_key):
        return _Iq()


class _NativeProducer:
    spec = NATIVE_KNOWN_PILOT_EVIDENCE_STAGE

    def __init__(self, product) -> None:
        self._product = product

    def analyze(self, _context, _iq, _products, outputs):
        published = outputs.publish_json(
            self.spec.output_products[0],
            self._product.model_dump(mode="json"),
        )
        return StageResult(outcome=StageOutcome.COMPLETE, products=(published,))


class _InjectedSameKindProducer(_NativeProducer):
    spec = StageSpec(
        key="injected-native-copy",
        algorithm_version="adversarial-v1",
        configuration_schema="adversarial-native-copy-v1",
        output_products=(
            ProductSpec(
                kind="starlink.native-known-pilot-evidence",
                schema_version=2,
                role=ProductRole.SCIENTIFIC,
            ),
        ),
    )


class _Authority:
    def __init__(self, value) -> None:
        self._value = value

    def resolve(self, _context, _iq, _native):
        return self._value


def test_exact_native_product_selection_rejects_duplicate_catalog_rows() -> None:
    product = SimpleNamespace(
        product_id=1,
        run_id="run-a",
        stage_key="native-known-pilot-evidence",
        scope_key="stream-a",
        kind="starlink.native-known-pilot-evidence",
        schema_version=2,
        role="scientific",
        status="complete",
        available=True,
    )
    catalog = SimpleNamespace(
        run_seal_snapshot=lambda _run_id: SimpleNamespace(
            jobs=(
                SimpleNamespace(
                    stage_key="native-known-pilot-evidence",
                    scope_key="stream-a",
                    state="succeeded",
                    outcome="complete",
                ),
            ),
            products=(product, SimpleNamespace(**{**vars(product), "product_id": 2})),
        )
    )
    reader = CatalogArtifactProductReader(  # type: ignore[arg-type]
        catalog,
        object(),  # type: ignore[arg-type]
        run_id="run-a",
        scope_key="stream-a",
    )

    with pytest.raises(ValueError, match="ambiguous"):
        reader.read_json(TRUSTED_MATCHED_RECOVERY_STAGE.input_products[0])


def test_selected_v2_dag_registers_native_dependency_and_nonproduction_product(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
) -> None:
    system = _prepare_recording(processing_database, tmp_path / "bulk", "matched-v2-session")
    _add_release(processing_database, "matched-v2-release")
    binding = _binding(release="matched-v2-release")
    config = MatchedPilotAcceptanceConfigV1.create(detector_binding=binding)
    identity = _identity(
        session_id=system.session_id,
        stream_id="stream-a",
        manifest_digest=system.manifest_digest,
    )
    calibration = _calibration(identity)
    native = _native(
        identity,
        calibration,
        _decisions("native"),
        binding,
        run_id="matched-v2-run",
    )
    legacy = _legacy(identity, calibration, _decisions("legacy_reference"), binding)
    matched = TrustedMatchedRecoveryAnalyzer(
        _Authority(
            TrustedMatchedRecoveryBinding(
                config=config,
                path_identity=identity,
                calibration=calibration,
                legacy_execution=legacy,
            )
        )
    )
    service = ProcessingService(
        catalog=processing_database.catalog,
        artifacts=system.artifacts,
        registry=AnalyzerRegistry(
            (_InjectedSameKindProducer(native), _NativeProducer(native), matched)
        ),
        iq_readers=_IqProvider(),
        lease_for=timedelta(seconds=2),
        heartbeat_interval=timedelta(milliseconds=200),
    )
    service.create_reprocess_run(
        run_id="matched-v2-run",
        session_id=system.session_id,
        pipeline_release_id="matched-v2-release",
        input_manifest_digest=system.manifest_digest,
        scope_keys=("stream-a",),
        promotion_policy="evidence_only",
        stage_keys=(
            "injected-native-copy",
            NATIVE_KNOWN_PILOT_EVIDENCE_STAGE.key,
            TRUSTED_MATCHED_RECOVERY_STAGE.key,
        ),
    )

    executions = _execute_until_idle(service)
    assert {item.stage_key for item in executions} == {
        "injected-native-copy",
        NATIVE_KNOWN_PILOT_EVIDENCE_STAGE.key,
        TRUSTED_MATCHED_RECOVERY_STAGE.key,
    }
    assert executions[-1].stage_key == TRUSTED_MATCHED_RECOVERY_STAGE.key
    service.finalize_run("matched-v2-run")
    snapshot = processing_database.catalog.run_seal_snapshot("matched-v2-run")
    matched_product = next(
        item for item in snapshot.products if item.kind == "starlink.trusted-matched-recovery"
    )
    document = system.artifacts.read_json(
        matched_product.logical_uri,
        matched_product.digest,
    )
    assert document["receipt"]["production_accepted"] is False
    with processing_database.engine.connect() as connection:
        dependency = connection.execute(
            text(
                "SELECT output.kind, input.kind, input.stage_key "
                "FROM product_dependency dependency "
                "JOIN analysis_product output ON output.id = dependency.product_id "
                "JOIN analysis_product input ON input.id = dependency.input_product_id"
            )
        ).one()
    assert dependency == (
        "starlink.trusted-matched-recovery",
        "starlink.native-known-pilot-evidence",
        "native-known-pilot-evidence",
    )
    assert TRUSTED_MATCHED_RECOVERY_STAGE.key not in production_long_dwell_registry(
        ComputeTier.STANDARD
    ).keys
