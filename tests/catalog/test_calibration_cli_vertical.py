from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import zstandard as zstd
from typer.testing import CliRunner

from leo.application.calibration_operations import CalibrationOperations
from leo.application.calibration_runtime import (
    ImmutableCalibrationScopeProvider,
    PostgresCalibrationOperationsAdapter,
    ProcessingCalibrationQueueAdapter,
)
from leo.application.frequency_calibration import (
    ImmutableDocumentRefV1,
    RecordingStoreCalibrationAdapter,
    TrustedFrequencyCalibrationPromoter,
)
from leo.artifacts import AnalysisArtifactStore
from leo.cli.app import create_cli
from leo.cli.calibration import CalibrationCliBackend
from leo.cli.processing import LocalProcessingBackend, ProcessingServices
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.recording import RecordingChunkV1, RecordingManifestV1
from leo.pipeline import AnalyzerRegistry
from leo.processing import ProcessingService, RecordingIqReaderProvider
from leo.qualification.frequency_calibration import (
    CalibrationExtractorReceiptV1,
)
from leo.qualification.frequency_calibration_documents import (
    AnalysisArtifactTrustedDocumentAdapter,
    ImmutableCalibrationPlanStore,
)
from leo.qualification.frequency_calibration_native import (
    ReleaseLocalCalibrationExtractionV1,
)
from leo.qualification.frequency_calibration_stage import (
    CalibrationExtractorAnalyzer,
)
from leo.qualification.frequency_calibration_store import (
    AuthoritativeCalibrationResolver,
    ImmutableCalibrationPromotionStore,
)
from leo.qualification.native_execution import _WORKER_ENVIRONMENT_DIGEST
from leo.storage import RecordingStore
from tests.qualification.test_frequency_calibration import (
    DIGEST_A,
    RADIO_ID,
    _manifest,
    _ReleasePort,
)

from .conftest import CatalogHarness

_RUNNER = CliRunner()


class _InjectedReleaseLocalExecutor:
    """Injected boundary for reviewed release-worker execution itself."""

    def __init__(self, extractions: dict[str, CalibrationExtractorReceiptV1]) -> None:
        self._extractions = extractions

    def execute(self, *, plan, capture, reader, release):
        del reader
        extraction = self._extractions[capture.manifest.session_id]
        return ReleaseLocalCalibrationExtractionV1.create(
            release=release,
            execution_environment_digest=_WORKER_ENVIRONMENT_DIGEST,
            worker_output_digest="sha256:" + "4" * 64,
            iq_snapshot_digest="sha256:" + "5" * 64,
            plan_digest=plan.plan_digest,
            capture_envelope_digest=capture.envelope_digest,
            extraction=extraction,
        )


class _CliComposite:
    def __init__(
        self,
        calibration: CalibrationCliBackend,
        processing: LocalProcessingBackend,
    ) -> None:
        self._calibration = calibration
        self._processing = processing

    def __getattr__(self, name: str):
        target = self._processing if name == "worker" else self._calibration
        return getattr(target, name)


def test_cli_predeclare_queue_worker_promote_show_real_vertical(
    catalog_harness: CatalogHarness,
    tmp_path: Path,
) -> None:
    bulk_root = tmp_path / "bulk"
    qualification_root = tmp_path / "qualification"
    plan_root = qualification_root / "frequency-calibration-plans"
    promotion_root = qualification_root / "frequency-calibration-promotions"
    plan_root.mkdir(parents=True)
    promotion_root.mkdir()
    recordings = RecordingStore(bulk_root)
    artifacts = AnalysisArtifactStore(bulk_root)
    manifests = tuple(
        _materialize_recording(recordings, index, offset_hz=index * 100.0) for index in range(3)
    )
    repository = catalog_harness.repository
    repository.add_pipeline_release(
        release_id="test-release",
        code_revision="0123456789abcdef0123456789abcdef01234567",
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_A,
    )
    for manifest, manifest_digest, uri in manifests:
        repository.create_capture_session(
            session_id=manifest.session_id,
            source_type="live",
            state="committed",
            bundle_uri=uri,
            manifest_digest=manifest_digest,
        )

    plans = ImmutableCalibrationPlanStore(plan_root, clock_ns=lambda: 50)
    outputs = ImmutableCalibrationPromotionStore(
        promotion_root,
        clock_ns=lambda: 2_000_000_000_000,
    )
    # Deployment attestation and release-local execution are the two explicit
    # injected boundaries; CLI, worker, stores, digest verification and PG are real.
    releases = _ReleasePort()
    resolver = AuthoritativeCalibrationResolver(
        outputs,
        releases,
        allowed_release_ids=("test-release",),
    )
    extractions: dict[str, CalibrationExtractorReceiptV1] = {}
    analyzer = CalibrationExtractorAnalyzer(ImmutableCalibrationScopeProvider(plans, recordings))
    service = ProcessingService(
        catalog=repository,
        artifacts=artifacts,
        registry=AnalyzerRegistry((analyzer,)),
        iq_readers=RecordingIqReaderProvider(recordings),
    )
    queue = ProcessingCalibrationQueueAdapter(repository, service, recordings)
    catalog = PostgresCalibrationOperationsAdapter(repository, resolver, recordings)
    promoter = TrustedFrequencyCalibrationPromoter(
        plans=plans,
        recordings=RecordingStoreCalibrationAdapter(recordings),
        artifacts=AnalysisArtifactTrustedDocumentAdapter(artifacts),
        outputs=outputs,
        releases=releases,
        extractor_executor=_InjectedReleaseLocalExecutor(extractions),
    )
    calibration = CalibrationCliBackend(
        CalibrationOperations(
            plans=plans,
            releases=releases,
            queue=queue,
            promoter=promoter,
            resolver=resolver,
            catalog=catalog,
            pipeline_release_id="test-release",
        )
    )
    processing = LocalProcessingBackend(
        ProcessingServices(
            catalog=repository,
            recordings=recordings,
            artifacts=artifacts,
            processing=service,
            holds=object(),  # type: ignore[arg-type]
            retention=object(),  # type: ignore[arg-type]
            reconciliation=object(),  # type: ignore[arg-type]
            importer=object(),  # type: ignore[arg-type]
            corpus_ingest=object(),  # type: ignore[arg-type]
            pipeline_release_id="test-release",
        )
    )
    backend = _CliComposite(calibration, processing)
    app = create_cli(lambda: backend)  # type: ignore[arg-type,return-value]
    sessions = tuple(manifest.session_id for manifest, _digest, _uri in manifests)

    predeclared = _RUNNER.invoke(
        app,
        [
            "process",
            "calibration",
            "predeclare",
            "--plan-id",
            "cli-real-plan",
            "--radio-id",
            RADIO_ID,
            "--starlink-channel",
            "ch4",
            "--starlink-edge",
            "lower",
            *(item for session in sessions for item in ("--session", session)),
            "--json",
        ],
    )
    assert predeclared.exit_code == 0, predeclared.stdout
    predeclared_json = json.loads(predeclared.stdout)
    plan_ref = predeclared_json["payload"]["result"]["plan_ref"]
    plans.load(ImmutableDocumentRefV1.model_validate(plan_ref))

    queue_result = _RUNNER.invoke(
        app,
        [
            "process",
            "calibration",
            "queue",
            "--plan-uri",
            plan_ref["logical_uri"],
            "--plan-digest",
            plan_ref["digest"],
            "--json",
        ],
    )
    assert queue_result.exit_code == 0, queue_result.stdout
    worker = _RUNNER.invoke(
        app,
        ["process", "worker", "--worker-id", "cli-worker", "--max-jobs", "3", "--json"],
    )
    assert worker.exit_code == 0, worker.stdout
    assert json.loads(worker.stdout)["payload"]["finalized_count"] == 3
    for session_id in sessions:
        run_id = next(
            run_id
            for queued_session, run_id in json.loads(queue_result.stdout)["payload"]["result"][
                "session_run_ids"
            ]
            if queued_session == session_id
        )
        snapshot = repository.run_seal_snapshot(run_id)
        assert len(snapshot.products) == 1
        product = snapshot.products[0]
        extractions[session_id] = CalibrationExtractorReceiptV1.model_validate(
            artifacts.read_json(product.logical_uri, product.digest)
        )

    promote_arguments = [
        "process",
        "calibration",
        "promote",
        "--plan-uri",
        plan_ref["logical_uri"],
        "--plan-digest",
        plan_ref["digest"],
        "--promotion-id",
        "cli-real-promotion",
        "--calibration-id",
        "cli-real-calibration",
        "--calibration-set-id",
        "cli-real-set",
        "--json",
    ]
    promoted = _RUNNER.invoke(app, promote_arguments)
    assert promoted.exit_code == 0, promoted.stdout
    shown = _RUNNER.invoke(
        app,
        ["process", "calibration", "show", "cli-real-promotion", "--json"],
    )
    assert shown.exit_code == 0, shown.stdout
    assert (
        json.loads(shown.stdout)["payload"]["result"]
        == json.loads(promoted.stdout)["payload"]["result"]
    )


def _materialize_recording(
    store: RecordingStore,
    index: int,
    *,
    offset_hz: float,
    acceptance: bool = False,
) -> tuple[RecordingManifestV1, str, str]:
    manifest = _manifest(index)
    if acceptance:
        manifest = manifest.model_copy(update={"tags": ("ACCEPTANCE", "LIVE")})
    rng = np.random.default_rng(index)
    iq = rng.integers(-4, 5, size=(250_000, 2), dtype=np.int16)
    times = np.arange(25_000, dtype=np.float64) / 2_500_000.0
    tones = 800 * (
        np.exp(2j * np.pi * (-820_312.5 + offset_hz) * times)
        + np.exp(2j * np.pi * (820_312.5 + offset_hz) * times)
    )
    iq[:25_000, 0] += tones.real.astype(np.int16)
    iq[:25_000, 1] += tones.imag.astype(np.int16)
    raw = iq.astype("<i2", copy=False).tobytes()
    compressed = zstd.ZstdCompressor(level=1).compress(raw)
    compressed_digest = sha256_digest(compressed)
    raw_digest = sha256_digest(raw)
    chunks = tuple(
        RecordingChunkV1(
            chunk_index=chunk_index,
            relative_path=f"radio-a/iq-{chunk_index:06d}.ci16.zst",
            sample_start=chunk_index * 250_000,
            sample_count=250_000,
            uncompressed_bytes=len(raw),
            compressed_bytes=len(compressed),
            uncompressed_sha256=raw_digest,
            compressed_sha256=compressed_digest,
        )
        for chunk_index in range(600)
    )
    stream = manifest.streams[0].model_copy(update={"chunks": chunks})
    manifest = manifest.model_copy(update={"streams": (stream,)})
    created = datetime.fromtimestamp(
        manifest.created_utc_ns // 1_000_000_000,
        tz=UTC,
    )
    directory = (
        store.recordings_root
        / f"{created.year:04d}"
        / f"{created.month:02d}"
        / f"{created.day:02d}"
        / manifest.session_id
    )
    stream_directory = directory / "radio-a"
    stream_directory.mkdir(parents=True)
    first = stream_directory / "iq-000000.ci16.zst"
    first.write_bytes(compressed)
    for chunk_index in range(1, 600):
        os.link(first, stream_directory / f"iq-{chunk_index:06d}.ci16.zst")
    payload = canonical_json_bytes(manifest.model_dump(mode="json"))
    (directory / "manifest.json").write_bytes(payload)
    bundle = store.inspect(manifest.session_id)
    return manifest, sha256_digest(payload), bundle.uri
