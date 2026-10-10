"""Composition of verified fast windows with the existing leased job queue."""

from __future__ import annotations

import importlib.metadata
import json
import multiprocessing
import os
import platform
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from leo.artifacts import AnalysisArtifactStore
from leo.catalog import (
    CatalogNotFoundError,
    CatalogRepository,
    JobDefinition,
    PromotionPolicy,
    create_catalog_engine,
    create_session_factory,
)
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.fast_scan import FastScanPolicyV1, FastScanSegmentResultV1
from leo.pipeline import AnalyzerRegistry
from leo.processing.service import ProcessingService
from leo.scanner.fast_scan_analysis import FastScanAnalyzer
from leo.storage.fast_scan import FastScanReaderProvider, FastScanStore


def predictor_factory(edge, receivers):
    from leo.analysis.starlink.pilot_predictor import PilotPredictor, native_library_path

    return PilotPredictor(native_library_path(), edge, receivers)


def implementation_identity():
    """Pin installed source and native bytes, including dirty development builds."""
    from leo.analysis.starlink.pilot_predictor import native_library_path

    package = Path(__file__).resolve().parents[1]
    files = [
        p
        for component in ("analysis/starlink", "scanner", "contracts", "processing", "storage")
        for p in (package / component).glob("*.py")
    ]
    hashes = {str(p.relative_to(package)): sha256_digest(p.read_bytes()) for p in files}
    hashes["native"] = sha256_digest(native_library_path().read_bytes())
    environment = {
        "python": platform.python_version(),
        **{name: importlib.metadata.version(name) for name in ("numpy", "pydantic")},
    }
    return canonical_digest(hashes), canonical_digest(environment)


class FastScanProcessing:
    def __init__(self, catalog, root, *, run_ids=None, predictor=predictor_factory, detector=None):
        self.catalog = catalog
        self.store = FastScanStore(root)
        self.artifacts = AnalysisArtifactStore(Path(root))
        analyzer = FastScanAnalyzer(
            predictor, **({} if detector is None else {"detector": detector})
        )
        self.service = ProcessingService(
            catalog=catalog,
            artifacts=self.artifacts,
            registry=AnalyzerRegistry([analyzer]),
            iq_readers=FastScanReaderProvider(self.store),
            worker_run_ids=run_ids,
        )

    def queue(self, recording, policy):
        session_id, digest, inventory = self.store.ingest(recording)
        code, environment = implementation_identity()
        configuration = {
            "stages": {"fast-scan": policy.model_dump(mode="json")},
            "implementation_digest": code,
        }
        release = "fast-" + canonical_digest([code, environment, configuration]).split(":")[1][:32]
        run_id = "fast-" + canonical_digest([session_id, digest, release]).split(":")[1][:32]
        try:
            existing = self.catalog.capture_recording_identity(session_id)
            if existing.manifest_digest != digest:
                raise ValueError("fast-scan capture identity changed")
        except CatalogNotFoundError:
            self.catalog.create_capture_session(
                session_id=session_id,
                source_type="live",
                state="committed",
                bundle_uri=f"fastscan://{session_id}",
                manifest_digest=digest,
                attributes={"kind": "fast-scan", "recording_name": inventory["recording_name"]},
                tags=("fast-scan",),
            )
        self.catalog.add_pipeline_release(
            release_id=release,
            code_revision=code,
            environment_digest=environment,
            graph_digest=canonical_digest(["fast-scan-fractional-v1"]),
            configuration=configuration,
            executable_digest=code,
        )
        try:
            self.catalog.run_state(run_id)
        except CatalogNotFoundError:
            self.catalog.create_analysis_run(
                run_id=run_id,
                session_id=session_id,
                pipeline_release_id=release,
                input_manifest_digest=digest,
                jobs=tuple(
                    JobDefinition(stage_key="fast-scan", scope_key=e["scope"], resource_class="cpu")
                    for e in inventory["segments"]
                ),
                trigger="reprocess",
                promotion_policy=PromotionPolicy.EVIDENCE_ONLY,
            )
        return run_id

    def publish(self, run_id):
        if self.catalog.run_state(run_id).value != "succeeded":
            self.service.finalize_run(run_id)
        snapshot = self.catalog.run_seal_snapshot(run_id)
        inventory = self.store.source(
            snapshot.execution.session_id, snapshot.execution.input_manifest_digest
        )
        segments = [
            FastScanSegmentResultV1.model_validate(
                self.artifacts.read_json(p.logical_uri, p.digest)
            )
            for p in snapshot.products
            if p.kind == "fast-scan.glrt"
        ]
        windows = sorted((w for s in segments for w in s.windows), key=lambda w: w.visit)
        if len(windows) != inventory["window_count"] or len({w.visit for w in windows}) != len(
            windows
        ):
            raise ValueError("fast-scan output does not cover the sealed input inventory")
        origin = min((w.sample_start for w in windows if w.sample_start is not None), default=0)
        policy = segments[0].policy
        counts = {
            status: sum(w.status == status for w in windows)
            for status in ("processed", "skipped_fast_score", "invalid_capture")
        }
        channels = {}
        points = []
        for w in windows:
            for score in w.scores:
                key = (w.channel, score.receiver_id)
                row = channels.setdefault(
                    key,
                    {
                        "channel": w.channel,
                        "receiver_id": score.receiver_id,
                        "processed": 0,
                        "skipped": 0,
                        "active": 0,
                        "strong": 0,
                    },
                )
                if w.status != "processed":
                    row["skipped"] += 1
                    continue
                row["processed"] += 1
                receiver = next(r for r in w.receivers if r.receiver_id == score.receiver_id)
                candidates = [c for c in receiver.candidates if c.fractional_margin is not None]
                if not candidates:
                    continue
                best = max(candidates, key=lambda c: c.fractional_margin)
                margin = best.fractional_margin
                row["active"] += int(margin >= policy.margin_gate)
                row["strong"] += int(margin >= policy.strong_margin)
                points.append(
                    {
                        "visit": w.visit,
                        "channel": w.channel,
                        "receiver_id": score.receiver_id,
                        "time_s": None
                        if w.sample_start is None
                        else (w.sample_start - origin) / policy.sample_rate_hz,
                        "score": score.margin,
                        "margin": margin,
                        "cfo_hz": best.fractional_tracking_cfo_hz,
                    }
                )
        report = {
            "schema_version": 1,
            "kind": "fast-scan.report",
            "run_id": run_id,
            "session_id": snapshot.execution.session_id,
            "recording_name": inventory["recording_name"],
            "policy": policy.model_dump(mode="json"),
            "counts": counts,
            "window_count": len(windows),
            "time_basis": "relative sample counter; UTC not inferred",
            "rf_mapping_authorities": sorted({w.rf_mapping_authority for w in windows}),
            "qualified_tracking": False,
            "channels": [channels[k] for k in sorted(channels)],
            "points": points,
        }
        self.store.publish(run_id, report)
        return report

    def tracking_input(self, run_id):
        """Adapt sealed results to the deployed shared scanner TrackingInput port.

        No tracking algorithm or old capture layout is recreated here. Clock
        evidence is transported separately for the existing timing constructor.
        """
        from leo.storage.fast_scan import FastSegmentSource

        if self.catalog.run_state(run_id).value != "succeeded":
            raise ValueError("tracking requires a sealed GLRT run")
        snapshot = self.catalog.run_seal_snapshot(run_id)
        inventory = self.store.source(
            snapshot.execution.session_id, snapshot.execution.input_manifest_digest
        )
        segments = [FastScanSegmentResultV1.model_validate(
            self.artifacts.read_json(p.logical_uri, p.digest))
            for p in snapshot.products if p.kind == "fast-scan.glrt"]
        windows = sorted((w for s in segments for w in s.windows), key=lambda w: w.visit)
        if len(windows) != inventory["window_count"] or any(
            w.visit != i for i, w in enumerate(windows)
        ):
            raise ValueError("tracking requires complete ordered window coverage")
        probes = []
        for w in windows:
            if w.status == "invalid_capture":
                raise ValueError("tracking input has invalid sample support")
            for receiver in w.receivers:
                candidates = []
                for c in receiver.candidates:
                    if c.fractional_epoch_status != "complete" or any(v is None for v in (
                        c.fractional_epoch_offset_samples, c.fractional_tracking_cfo_hz,
                        c.fractional_exact_score, c.fractional_control_score, c.fractional_margin
                    )):
                        continue
                    candidates.append({
                        "candidate_rank": c.candidate_rank,
                        "integer_epoch_sample": c.epoch_sample,
                        "fractional_epoch_offset_samples": c.fractional_epoch_offset_samples,
                        "fractional_tracking_cfo_hz": c.fractional_tracking_cfo_hz,
                        "fractional_exact_score": c.fractional_exact_score,
                        "fractional_control_score": c.fractional_control_score,
                        "fractional_margin": c.fractional_margin,
                        "passed_fractional_margin_gate": c.fractional_margin >= 0.025,
                    })
                probes.append({
                    "visit_index": w.visit, "receiver_id": receiver.receiver_id,
                    "probe_index": 0, "probe_start_ms": 0, "channel": w.channel,
                    "edge": w.edge, "actual_rf_hz": float(w.actual_if_hz + w.lnb_reference_hz),
                    "valid_start_counter": w.sample_start,
                    # Payload indexing excludes guard/gaps; timing uses hardware counters.
                    "payload_start_sample": w.visit * 50000, "candidates": candidates,
                })
        anchor = None
        clocks = []
        radio = None
        for entry in inventory["segments"]:
            source = FastSegmentSource(entry)
            radio = source.radio
            for w in source.windows():
                receipt = json.loads(w.acquisition.get("retune_receipt") or "{}")
                if "utc_clock_bracket" in receipt:
                    if anchor is not None:
                        raise ValueError("multiple UTC anchors in one stream")
                    anchor = receipt["utc_clock_bracket"]
                if "host_delivery_clock" in receipt:
                    clocks.append(receipt["host_delivery_clock"])
        return {
            "source": {
                "session_id": snapshot.execution.session_id, "capture_mode": "adaptive",
                "sample_rate_hz": 2500000, "radio_id": radio["serial"],
                "stream_generation": f"continuous-iio-{windows[0].generation:016x}",
                "input_manifest_sha256": snapshot.execution.input_manifest_digest,
                "analysis_manifest_sha256": canonical_digest([
                    s.model_dump(mode="json") for s in segments]),
                "raw_recording_authority_digest": canonical_digest([
                    snapshot.execution.input_manifest_digest, [w.iq_sha256 for w in windows]]),
                "qualified": True, "timing": None, "probes": probes, "probe_ms": 20,
                "capture_start_utc_ns": None, "capture_end_utc_ns": None,
            },
            "clock_anchor": anchor, "delivery_clocks": clocks,
            "last_sample_counter": windows[-1].sample_end,
            "provenance": {
                "run_id": run_id, "window_count": len(windows),
                "skipped_fast_score": sum(w.status == "skipped_fast_score" for w in windows),
                "rf_mapping_authorities": sorted({w.rf_mapping_authority for w in windows}),
                "scope": "conditional on the recorded LNB reference hypotheses",
            },
        }


def _worker(database_url, root, run_id, expected_identity):
    if implementation_identity() != expected_identity:
        raise RuntimeError("fast-scan worker implementation differs from queued release")
    engine = create_catalog_engine(database_url)
    try:
        app = FastScanProcessing(
            CatalogRepository(create_session_factory(engine)), root, run_ids=(run_id,)
        )
        execution = app.catalog.run_execution_info(run_id)
        if (
            execution.pipeline_configuration.get("implementation_digest"),
            execution.environment_digest,
        ) != expected_identity:
            raise RuntimeError("fast-scan worker does not match the persisted release")
        completed = 0
        while app.service.run_once(worker_id=f"fast-scan-{os.getpid()}") is not None:
            completed += 1
        return completed
    finally:
        engine.dispose()


def process_recording(recording, *, database_url, root, policy=None, workers=8,
                      export_tracking_input=False):
    if not 1 <= workers <= 32:
        raise ValueError("workers must be between 1 and 32")
    policy = policy or FastScanPolicyV1()
    engine = create_catalog_engine(database_url)
    try:
        app = FastScanProcessing(CatalogRepository(create_session_factory(engine)), root)
        run_id = app.queue(recording, policy)
        identity = implementation_identity()
        # Spawn prevents sharing DB connections or native scratch buffers across processes.
        with ProcessPoolExecutor(
            max_workers=workers, mp_context=multiprocessing.get_context("spawn")
        ) as pool:
            futures = [
                pool.submit(_worker, database_url, str(root), run_id, identity)
                for _ in range(workers)
            ]
            for future in futures:
                future.result()
        report = app.publish(run_id)
        if export_tracking_input:
            app.store.publish_tracking_input(run_id, app.tracking_input(run_id))
        return report
    finally:
        engine.dispose()
