"""Authoritative Standard-v2 projection over sealed catalog products."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from leo.analysis.standard.codecs import decode_standard_product
from leo.analysis.standard.products import PATH_PRESENTATION_PRODUCT
from leo.artifacts import AnalysisArtifactStore, AnalysisRunManifestV1
from leo.catalog import CatalogRepository
from leo.catalog.types import CatalogJobRecord, CatalogProductRecord, CatalogSessionReadSnapshot
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import StandardPathInputBindV2
from leo.pipeline.scopes import ScopeKind
from leo.presentation.standard_pipeline import (
    StandardAxisBoundsV2,
    StandardCfoObservationV2,
    StandardComputationDispositionV2,
    StandardLaneSourceExtremaV2,
    StandardMetricSeriesV2,
    StandardPathEvidenceV2,
    StandardPipelineReleaseV2,
    StandardPlotViewV2,
    StandardReceiverPathRefV2,
    StandardReuseSummaryV2,
    StandardSeriesPointV2,
    StandardSourceAxisExtremaV2,
    StandardSourceAxisIdV2,
    StandardSourceExtremaProofV2,
    StandardSourceTypeV2,
    StandardStageStatusV2,
    StandardSubjectDetailV2,
    StandardSubjectHierarchyV2,
    StandardSubjectKindV2,
    StandardSubjectStateV2,
    StandardSubjectSummaryV2,
    StandardTimeDomainV2,
    StandardTrajectoryCurveV2,
    StandardTrajectoryRowV2,
    StandardUnitV2,
    StandardViewDescriptorV2,
    StandardViewKindV2,
    StandardViewStateV2,
    StandardWaterfallCellV2,
    standard_eligibility_v2,
    standard_source_extrema_from_lanes_v2,
)


class StandardPresentationUnavailable(RuntimeError):
    """The selected run or one of its immutable presentation inputs is invalid."""


@dataclass(frozen=True, slots=True)
class _PathSource:
    product: CatalogProductRecord
    binding: StandardPathInputBindV2
    document: dict[str, Any]
    reference: StandardReceiverPathRefV2


@dataclass(frozen=True, slots=True)
class _Projection:
    snapshot: CatalogSessionReadSnapshot
    run_id: str
    manifest_digest: str
    release: StandardPipelineReleaseV2
    paths: tuple[_PathSource, ...]
    jobs: tuple[CatalogJobRecord, ...]
    hierarchy: StandardSubjectHierarchyV2
    subjects: dict[str, StandardSubjectSummaryV2]


class CatalogStandardPresentationRepository:
    """Read sealed Standard products without consulting IQ or fixture data."""

    def __init__(self, catalog: CatalogRepository, artifacts: AnalysisArtifactStore) -> None:
        self._catalog = catalog
        self._artifacts = artifacts

    def subject_hierarchy(self, session_id: str) -> StandardSubjectHierarchyV2 | None:
        loaded = self._load(session_id)
        return None if loaded is None else loaded.hierarchy

    def subject_detail(self, session_id: str, subject_id: str) -> StandardSubjectDetailV2 | None:
        loaded = self._load(session_id)
        if loaded is None or subject_id not in loaded.subjects:
            return None
        subject = loaded.subjects[subject_id]
        selected = self._subject_paths(loaded, subject)
        domain = _time_domain(selected)
        trajectories = _trajectory_rows(selected)
        stages = _stage_rows(loaded, subject, selected)
        views = tuple(
            StandardViewDescriptorV2(
                view_kind=kind,
                state=StandardViewStateV2.AVAILABLE,
                href=(
                    f"/api/v2/recordings/{session_id}/standard-subjects/"
                    f"{subject_id}/views/{kind.value}"
                ),
                source_point_count=_source_count(selected, kind),
                reason="Bounded registered presentation is available",
            )
            for kind in StandardViewKindV2
        )
        path_subjects = tuple(loaded.subjects[path.reference.subject_id] for path in selected)
        return StandardSubjectDetailV2(
            subject=subject,
            time_domain=domain,
            receiver_path_expansions=path_subjects,
            receiver_path_evidence=tuple(_path_evidence(path) for path in selected),
            stage_source_count=len(stages),
            stages=stages,
            stages_truncated=False,
            trajectory_source_count=len(trajectories),
            trajectories=trajectories[:256],
            trajectories_truncated=len(trajectories) > 256,
            views=views,
            limitations=(
                "Candidate evidence only; source identity is unassessed; "
                "no payload recovery is claimed",
                "Cross-radio evidence is score/trajectory-level and is not phase coherent",
            ),
        )

    def subject_view(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        *,
        maximum_points: int,
    ) -> StandardPlotViewV2 | None:
        loaded = self._load(session_id)
        if loaded is None or subject_id not in loaded.subjects:
            return None
        subject = loaded.subjects[subject_id]
        return _build_view(
            loaded,
            subject,
            self._subject_paths(loaded, subject),
            view_kind,
            maximum_points=maximum_points,
        )

    def verify_source_extrema(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        proof: StandardSourceExtremaProofV2,
    ) -> bool:
        loaded = self._load(session_id, include_documents=False)
        if loaded is None or subject_id not in loaded.subjects:
            return False
        subject = loaded.subjects[subject_id]
        selected = self._subject_paths(loaded, subject)
        expected_content = _digest(
            canonical_digest(
                {
                    "view_kind": view_kind.value,
                    "products": [item.product.digest for item in selected],
                }
            )
        )
        return (
            proof.source_artifact_digest == loaded.manifest_digest
            and proof.source_content_digest == expected_content
        )

    @staticmethod
    def _subject_paths(
        loaded: _Projection, subject: StandardSubjectSummaryV2
    ) -> tuple[_PathSource, ...]:
        wanted = {item.path_id for item in subject.receiver_paths}
        return tuple(item for item in loaded.paths if item.reference.path_id in wanted)

    def _load(self, session_id: str, *, include_documents: bool = True) -> _Projection | None:
        try:
            snapshot = self._catalog.presentation_snapshot(session_id)
            if snapshot is None or snapshot.analysis is None:
                return None
            analysis = snapshot.analysis
            source_type = StandardSourceTypeV2(snapshot.source_type.upper())
            if source_type is StandardSourceTypeV2.TEST:
                if analysis.promotion_policy != "evidence_only" or analysis.is_current:
                    raise StandardPresentationUnavailable(
                        "TEST Standard evidence must be sealed evidence-only and non-current"
                    )
            elif not analysis.is_current or analysis.promotion_policy != "current":
                raise StandardPresentationUnavailable(
                    "ordinary Standard presentation requires the exact current run"
                )
            if (
                analysis.state != "succeeded"
                or analysis.sealed_at is None
                or analysis.manifest_uri is None
                or analysis.manifest_digest is None
            ):
                raise StandardPresentationUnavailable("Standard analysis run is not sealed")
            reference = self._catalog.run_manifest_reference(analysis.run_id)
            if (
                reference.logical_uri != analysis.manifest_uri
                or reference.digest != analysis.manifest_digest
            ):
                raise StandardPresentationUnavailable("catalog run-manifest authority drifted")
            manifest = AnalysisRunManifestV1.model_validate(
                self._artifacts.read_json(reference.logical_uri, reference.digest)
            )
            execution = self._catalog.run_execution_info(analysis.run_id)
            seal = self._catalog.run_seal_snapshot(analysis.run_id)
            if (
                manifest.run_id != analysis.run_id
                or manifest.session_id != session_id
                or manifest.pipeline_release_id != analysis.pipeline_release_id
                or manifest.input_manifest_digest != analysis.input_manifest_digest
                or execution.session_id != session_id
            ):
                raise StandardPresentationUnavailable("sealed Standard manifest identity drifted")
            manifest_products = {
                (
                    item.product_id,
                    item.stage_key,
                    item.scope_key,
                    item.kind,
                    item.product_schema_version,
                    item.role,
                    item.status,
                    item.media_type,
                    item.logical_uri,
                    item.digest,
                    item.byte_size,
                    item.coverage,
                )
                for item in manifest.products
            }
            catalog_products = {
                (
                    item.product_id,
                    item.stage_key,
                    item.scope_key,
                    item.kind,
                    item.schema_version,
                    item.role,
                    item.status,
                    item.media_type,
                    item.logical_uri,
                    item.digest,
                    item.byte_size,
                    item.coverage,
                )
                for item in seal.products
            }
            if manifest_products != catalog_products:
                raise StandardPresentationUnavailable(
                    "sealed Standard manifest product inventory drifted"
                )
            manifest_jobs = {
                (item.job_id, item.stage_key, item.scope_key, item.outcome)
                for item in manifest.jobs
            }
            catalog_jobs = {
                (item.job_id, item.stage_key, item.scope_key, item.outcome) for item in seal.jobs
            }
            if manifest_jobs != catalog_jobs:
                raise StandardPresentationUnavailable(
                    "sealed Standard manifest job inventory drifted"
                )
            if (
                not execution.code_revision
                or execution.code_revision != analysis.pipeline_release_id
            ):
                raise StandardPresentationUnavailable(
                    "Standard release is not exact source authority"
                )
            release = StandardPipelineReleaseV2(
                authoritative_pipeline_release_id=execution.pipeline_release_id,
                source_revision=execution.code_revision,
                display_version=str(
                    execution.pipeline_configuration.get("display_version", "2.0.0")
                ),
                graph_digest=_digest(execution.graph_digest),
                configuration_digest=_digest(execution.configuration_digest),
                environment_digest=_digest(execution.environment_digest),
            )
            candidates = tuple(
                item
                for item in seal.products
                if item.kind == PATH_PRESENTATION_PRODUCT.kind
                and item.schema_version == PATH_PRESENTATION_PRODUCT.schema_version
                and item.role == "presentation"
                and item.available
            )
            if not candidates:
                raise StandardPresentationUnavailable(
                    "sealed run has no Standard path presentation products"
                )
            if any(job.state != "succeeded" for job in seal.jobs):
                raise StandardPresentationUnavailable(
                    "sealed Standard run contains a nonterminal job"
                )
            paths = tuple(
                self._load_path(
                    analysis.run_id,
                    item,
                    include_document=include_documents,
                )
                for item in candidates
            )
            paths = tuple(
                sorted(
                    paths,
                    key=lambda item: (
                        item.binding.stream_id,
                        item.binding.receiver_id,
                    ),
                )
            )
            if len(paths) != len({item.reference.scope_digest for item in paths}) or len(paths) > 4:
                raise StandardPresentationUnavailable(
                    "Standard path presentation inventory is duplicated or unbounded"
                )
            streams = {item.binding.stream_id for item in paths}
            radio_products = tuple(
                item
                for item in seal.products
                if item.kind == "standard.radio-report"
                and item.schema_version == 1
                and item.available
                and item.scope is not None
                and item.scope.kind is ScopeKind.RADIO
            )
            paired_products = tuple(
                item
                for item in seal.products
                if item.kind == "standard.paired-report"
                and item.schema_version == 1
                and item.available
                and item.scope is not None
                and item.scope.kind is ScopeKind.PAIRED
            )
            if {
                item.scope.stream_id for item in radio_products if item.scope is not None
            } != streams:
                raise StandardPresentationUnavailable(
                    "sealed Standard run lacks exact radio reducers"
                )
            if (len(streams) == 2 and len(paired_products) != 1) or (
                len(streams) == 1 and paired_products
            ):
                raise StandardPresentationUnavailable(
                    "sealed Standard run lacks the exact paired reducer inventory"
                )
            paths = _normalize_path_labels(paths)
            hierarchy, subjects = _hierarchy(snapshot, analysis.sealed_at, release, paths)
            return _Projection(
                snapshot=snapshot,
                run_id=analysis.run_id,
                manifest_digest=_digest(analysis.manifest_digest),
                release=release,
                paths=paths,
                jobs=seal.jobs,
                hierarchy=hierarchy,
                subjects=subjects,
            )
        except StandardPresentationUnavailable:
            raise
        except Exception as error:
            raise StandardPresentationUnavailable(
                "Standard presentation authority or artifact is unavailable"
            ) from error

    def _load_path(
        self,
        run_id: str,
        product: CatalogProductRecord,
        *,
        include_document: bool,
    ) -> _PathSource:
        scope = product.scope
        if scope is None or scope.kind is not ScopeKind.RECEIVER_PATH:
            raise StandardPresentationUnavailable("path presentation lacks typed path scope")
        binding = StandardPathInputBindV2.model_validate(
            self._catalog.run_subject_binding(run_id, scope).document
        )
        document = (
            decode_standard_product(
                PATH_PRESENTATION_PRODUCT,
                self._artifacts.read_json(product.logical_uri, product.digest),
            )
            if include_document
            else {}
        )
        if (
            binding.session_id != scope.session_id
            or binding.stream_id != scope.stream_id
            or binding.receiver_id != scope.receiver_id
        ):
            raise StandardPresentationUnavailable("path presentation source binding drifted")
        if include_document and (
            document["sample_rate_hz"] != binding.sample_rate_hz
            or document["declared_sample_count"] != binding.declared_sample_count
        ):
            raise StandardPresentationUnavailable("path presentation source binding drifted")
        path_id = f"{binding.radio_id}:rx{binding.receiver_id}"
        return _PathSource(
            product=product,
            binding=binding,
            document=document,
            reference=StandardReceiverPathRefV2(
                subject_id=f"path:{path_id}",
                path_id=path_id,
                radio_id=binding.radio_id,
                radio_label="Radio0",  # replaced by the canonical hierarchy label
                receiver_id=binding.receiver_id,
                receiver_label=f"RX{binding.receiver_id}",
                scope=scope,
                scope_digest=_digest(scope.canonical_digest),
            ),
        )


def _hierarchy(
    snapshot: CatalogSessionReadSnapshot,
    generated_at: datetime,
    release: StandardPipelineReleaseV2,
    sources: tuple[_PathSource, ...],
) -> tuple[StandardSubjectHierarchyV2, dict[str, StandardSubjectSummaryV2]]:
    source_type = StandardSourceTypeV2(snapshot.source_type.upper())
    eligibility = standard_eligibility_v2(
        source_type,
        snapshot.tags,
        capture_committed=snapshot.state == "committed",
        capture_healthy=snapshot.state == "committed",
    )
    streams = tuple(sorted({item.binding.stream_id for item in sources}))
    if not 1 <= len(streams) <= 2:
        raise StandardPresentationUnavailable("Standard hierarchy requires one or two radios")
    radio_labels = {stream: f"Radio{index}" for index, stream in enumerate(streams)}
    state = (
        StandardSubjectStateV2.COMPLETE
        if eligibility.evidence_only
        else StandardSubjectStateV2.CURRENT
    )

    def subject(
        subject_id: str,
        kind: StandardSubjectKindV2,
        label: str,
        paths: tuple[StandardReceiverPathRefV2, ...],
        children: tuple[str, ...],
    ) -> StandardSubjectSummaryV2:
        return StandardSubjectSummaryV2(
            subject_id=subject_id,
            session_id=snapshot.session_id,
            subject_kind=kind,
            label=label,
            derived=kind is not StandardSubjectKindV2.RECEIVER_PATH,
            receiver_paths=paths,
            expected_path_count=len(paths),
            completed_path_count=len(paths),
            child_subject_ids=children,
            state=state,
            ordinary_current=not eligibility.evidence_only,
            state_reasons=(),
            pipeline_release=release,
            desired_pipeline_release_id=release.authoritative_pipeline_release_id,
            reuse=StandardReuseSummaryV2(
                computed_stage_count=1,
                reused_stage_count=0,
                recompute_stage_count=0,
                reason="Rendered for this run",
            ),
            eligibility=eligibility,
        )

    path_subjects = tuple(
        subject(
            item.reference.subject_id,
            StandardSubjectKindV2.RECEIVER_PATH,
            f"{item.reference.radio_label} {item.reference.receiver_label}",
            (item.reference,),
            (),
        )
        for item in sources
    )
    radios = tuple(
        subject(
            f"radio:{stream}",
            StandardSubjectKindV2.RADIO,
            radio_labels[stream],
            tuple(item.reference for item in sources if item.binding.stream_id == stream),
            tuple(
                item.reference.subject_id for item in sources if item.binding.stream_id == stream
            ),
        )
        for stream in streams
    )
    rows: tuple[StandardSubjectSummaryV2, ...]
    all_subjects = (*path_subjects, *radios)
    if len(radios) == 2:
        pair = subject(
            f"pair:{streams[0]}:{streams[1]}",
            StandardSubjectKindV2.PAIRED,
            "Paired Radio0 + Radio1",
            tuple(path for radio in radios for path in radio.receiver_paths),
            tuple(radio.subject_id for radio in radios),
        )
        rows = (pair, *radios)
        all_subjects = (*all_subjects, pair)
    else:
        rows = radios
    hierarchy = StandardSubjectHierarchyV2(
        session_id=snapshot.session_id,
        source_type=source_type,
        eligibility=eligibility,
        generated_at=generated_at,
        rows=rows,
    )
    return hierarchy, {item.subject_id: item for item in all_subjects}


def _normalize_path_labels(sources: tuple[_PathSource, ...]) -> tuple[_PathSource, ...]:
    streams = tuple(sorted({item.binding.stream_id for item in sources}))
    labels = {stream: f"Radio{index}" for index, stream in enumerate(streams)}
    return tuple(
        _PathSource(
            product=item.product,
            binding=item.binding,
            document=item.document,
            reference=item.reference.model_copy(
                update={"radio_label": labels[item.binding.stream_id]}
            ),
        )
        for item in sources
    )


def _time_domain(paths: tuple[_PathSource, ...]) -> StandardTimeDomainV2:
    first = min(item.binding.timing.first_estimate_utc_ns for item in paths)
    last = max(item.binding.timing.last_estimate_utc_ns for item in paths)
    uncertainty_ns = max(
        max(
            item.binding.timing.first_estimate_utc_ns - item.binding.timing.first_earliest_utc_ns,
            item.binding.timing.first_latest_utc_ns - item.binding.timing.first_estimate_utc_ns,
            item.binding.timing.last_estimate_utc_ns - item.binding.timing.last_earliest_utc_ns,
            item.binding.timing.last_latest_utc_ns - item.binding.timing.last_estimate_utc_ns,
        )
        for item in paths
    )
    duration = (last - first) / 1_000_000_000
    return StandardTimeDomainV2(
        absolute_start_utc=datetime.fromtimestamp(first / 1_000_000_000, UTC),
        absolute_end_utc=datetime.fromtimestamp(last / 1_000_000_000, UTC),
        elapsed_end_s=duration,
        timing_uncertainty_s=uncertainty_ns / 1_000_000_000 + 1e-9,
    )


def _path_evidence(path: _PathSource) -> StandardPathEvidenceV2:
    timeline = path.document["power_timeline"]
    declared = path.binding.declared_sample_count / path.binding.sample_rate_hz
    analyzed = timeline["observed_sample_count"] / path.binding.sample_rate_hz
    frequency = path.binding.frequency_reference
    applicable = frequency.reference.value == "calibrated"
    return StandardPathEvidenceV2(
        receiver_path=path.reference,
        coverage_fraction=min(1.0, analyzed / declared),
        analyzed_seconds=analyzed,
        declared_seconds=declared,
        quality_state="complete" if analyzed == declared else "partial",
        clipped_fraction=None,
        continuity_gap_count=int(timeline["uncovered_region_count"]),
        calibration_state="applicable" if applicable else "unavailable",
        calibration_id=(
            f"calibration:{_digest(frequency.calibration_digest)}" if applicable else None
        ),
        calibration_digest=_digest(frequency.calibration_digest) if applicable else None,
        frequency_uncertainty_hz=frequency.uncertainty_hz if applicable else None,
        reason=(
            "Full path coverage with capture-epoch calibration"
            if applicable and analyzed == declared
            else "Candidate analysis state projected exactly"
        ),
    )


def _stage_rows(
    loaded: _Projection,
    subject: StandardSubjectSummaryV2,
    paths: tuple[_PathSource, ...],
) -> tuple[StandardStageStatusV2, ...]:
    scopes = {item.reference.scope.canonical_digest for item in paths}
    rows = []
    path_products = {item.product.scope_key: item.product for item in paths}
    for job in loaded.jobs:
        if job.scope is None:
            continue
        if job.scope.kind is ScopeKind.RECEIVER_PATH:
            if job.scope.canonical_digest not in scopes:
                continue
        elif job.scope.kind is ScopeKind.RADIO:
            if subject.subject_kind is StandardSubjectKindV2.RECEIVER_PATH or (
                subject.subject_kind is StandardSubjectKindV2.RADIO
                and job.scope.stream_id not in {item.binding.stream_id for item in paths}
            ):
                continue
        elif subject.subject_kind is not StandardSubjectKindV2.PAIRED:
            continue
        digest = path_products.get(job.scope_key)
        rows.append(
            StandardStageStatusV2(
                stage_key=job.stage_key,
                subject_id=subject.subject_id,
                disposition=StandardComputationDispositionV2.COMPUTED,
                output_digest=None if digest is None else _digest(digest.digest),
                reason="Rendered for this run",
            )
        )
    return tuple(rows[:256])


def _trajectory_rows(paths: tuple[_PathSource, ...]) -> tuple[StandardTrajectoryRowV2, ...]:
    rows = []
    for path in paths:
        offset_s = _path_time_offset_s(path, paths)
        for item in path.document["trajectory_table"]["trajectories"]:
            selected = bool(item["selected_for_correction"])
            rows.append(
                StandardTrajectoryRowV2(
                    trajectory_id=item["trajectory_id"],
                    receiver_path_id=path.reference.path_id,
                    algorithm=item["model"],
                    degree=item["polynomial_degree"],
                    reference_time_s=item["reference_time_s"] + offset_s,
                    coefficients_hz=tuple(item["coefficients_hz"]),
                    support_count=item["point_count"],
                    residual_rms_hz=item["residual_rms_hz"],
                    bic=item["bic"],
                    selected_for_correction=selected,
                    corrected_glrt64_gain=item["median_glrt64_margin_delta"],
                    status="selected" if selected else "retained",
                )
            )
    return tuple(rows)


def _build_view(
    loaded: _Projection,
    subject: StandardSubjectSummaryV2,
    paths: tuple[_PathSource, ...],
    kind: StandardViewKindV2,
    *,
    maximum_points: int,
) -> StandardPlotViewV2:
    if maximum_points < len(paths) or maximum_points > 2048:
        raise ValueError("maximum_points must cover every receiver path and be at most 2,048")
    if kind is StandardViewKindV2.WATERFALL:
        return _waterfall_view(loaded, subject, paths, maximum_points)
    if kind is StandardViewKindV2.CFO_TRAJECTORY:
        return _cfo_view(loaded, subject, paths, maximum_points)
    return _metric_view(loaded, subject, paths, kind, maximum_points)


def _source_count(paths: tuple[_PathSource, ...], kind: StandardViewKindV2) -> int:
    count = 0
    for path in paths:
        document = path.document
        detections = document["pilot_scan"]["detections"]
        if kind in {StandardViewKindV2.QUALITY, StandardViewKindV2.POWER}:
            count += len(document["power_timeline"]["timeline"])
        elif kind is StandardViewKindV2.WATERFALL:
            waterfall = document["waterfall"]
            count += len(waterfall["tiles"]) * len(waterfall["frequency_bin_centers_hz"])
        elif kind is StandardViewKindV2.QAM:
            count += 2 * len(detections)
        elif kind is StandardViewKindV2.GLRT64:
            count += sum(
                any(score["method"] == "glrt64" for score in item["scores"]) for item in detections
            )
            count += len(document["trajectory_feedback"]["results"])
        else:
            count += sum(
                any(score["method"] == "glrt64" for score in item["scores"]) for item in detections
            )
            count += 17 * len(document["trajectory_table"]["trajectories"])
    return count


def _metric_view(
    loaded: _Projection,
    subject: StandardSubjectSummaryV2,
    paths: tuple[_PathSource, ...],
    kind: StandardViewKindV2,
    maximum_points: int,
) -> StandardPlotViewV2:
    entries: list[tuple[str, str, str, StandardUnitV2, float, float]] = []
    for path in paths:
        lane = path.reference.path_id
        document = path.document
        offset_s = _path_time_offset_s(path, paths)
        if kind is StandardViewKindV2.POWER:
            for item in document["power_timeline"]["timeline"]:
                entries.append(
                    (
                        lane,
                        "window",
                        "Window power",
                        "dBFS",
                        offset_s + (item["time_start_s"] + item["time_stop_s"]) / 2,
                        item["mean_power_dbfs"],
                    )
                )
        elif kind is StandardViewKindV2.QUALITY:
            for item in document["power_timeline"]["timeline"]:
                fraction = item["observed_sample_count"] / max(
                    1, item["sample_stop"] - item["sample_start"]
                )
                entries.append(
                    (
                        lane,
                        "valid",
                        "Valid sample fraction",
                        "fraction",
                        offset_s + item["time_start_s"],
                        fraction,
                    )
                )
        elif kind is StandardViewKindV2.QAM:
            for item in document["pilot_scan"]["detections"]:
                entries.append(
                    (
                        lane,
                        "accuracy",
                        "Known-pilot QAM accuracy",
                        "accuracy",
                        offset_s + item["time_s"],
                        item["qam_accuracy"],
                    )
                )
                entries.append(
                    (
                        lane,
                        "evm",
                        "Known-pilot QAM RMS EVM",
                        "EVM",
                        offset_s + item["time_s"],
                        item["qam_evm"],
                    )
                )
        else:
            for item in document["pilot_scan"]["detections"]:
                score = next(
                    (score for score in item["scores"] if score["method"] == "glrt64"), None
                )
                if score is not None:
                    entries.append(
                        (
                            lane,
                            "initial",
                            "Initial GLRT64 detector response",
                            "response",
                            offset_s + item["time_s"],
                            score["exact_score"],
                        )
                    )
            for item in document["trajectory_feedback"]["results"]:
                entries.append(
                    (
                        lane,
                        "corrected",
                        "Trajectory-corrected GLRT64 candidate redetection response",
                        "response",
                        offset_s + item["time_s"],
                        item["corrected_margin"],
                    )
                )
    selected = _select_by_lane(entries, maximum_points, lambda item: item[0])
    if {item[0] for item in selected} != {path.reference.path_id for path in paths}:
        raise StandardPresentationUnavailable(f"{kind.value} has no evidence for every path")
    groups: dict[tuple[str, str, str, StandardUnitV2], list[tuple[float, float]]] = defaultdict(
        list
    )
    full_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for lane, metric, _label, _unit, _time_s, value in entries:
        full_groups[(lane, metric)].append(value)
    for lane, metric, label, unit, time_s, value in selected:
        groups[(lane, metric, label, unit)].append((time_s, value))
    series = tuple(
        StandardMetricSeriesV2(
            series_id=f"{kind.value}:{metric}:{lane}",
            receiver_path_id=lane,
            label=label,
            unit=unit,
            source_point_count=len(full_groups[(lane, metric)]),
            points=tuple(
                StandardSeriesPointV2(time_s=time_s, value=value) for time_s, value in values
            ),
            truncated=len(full_groups[(lane, metric)]) > len(values),
            source_min=min(full_groups[(lane, metric)]),
            source_max=max(full_groups[(lane, metric)]),
        )
        for (lane, metric, label, unit), values in groups.items()
    )
    lanes = tuple(
        _lane_extrema(
            path.reference.path_id,
            ("metric_value",),
            [item[5] for item in entries if item[0] == path.reference.path_id],
        )
        for path in paths
    )
    proof = _proof(loaded, paths, kind, lanes)
    returned = sum(len(item.points) for item in series)
    values = [item[5] for item in entries]
    return StandardPlotViewV2(
        session_id=loaded.snapshot.session_id,
        subject_id=subject.subject_id,
        view_kind=kind,
        state=StandardViewStateV2.AVAILABLE,
        time_domain=_time_domain(paths),
        receiver_path_ids=tuple(path.reference.path_id for path in paths),
        horizontal_axis=_time_axis(paths),
        vertical_axis=StandardAxisBoundsV2(
            axis_id="metric_value",
            label=_metric_axis_label(kind),
            unit="mixed" if len({item[3] for item in entries}) > 1 else entries[0][3],
            full_source_min=min(values),
            full_source_max=max(values),
        ),
        source_extrema=proof,
        source_point_count=proof.source_point_count,
        returned_point_count=returned,
        truncated=proof.source_point_count > returned,
        series=series,
        reason="Bounded aligned-time metric series",
    )


def _waterfall_view(
    loaded: _Projection,
    subject: StandardSubjectSummaryV2,
    paths: tuple[_PathSource, ...],
    maximum_points: int,
) -> StandardPlotViewV2:
    entries: list[tuple[str, float, float, float]] = []
    lanes = []
    for path in paths:
        waterfall = path.document["waterfall"]
        offset_s = _path_time_offset_s(path, paths)
        receiver_ids = tuple(waterfall["receiver_ids"])
        try:
            receiver_index = receiver_ids.index(path.binding.receiver_id)
        except ValueError as error:
            raise StandardPresentationUnavailable("waterfall receiver inventory drifted") from error
        frequencies = waterfall["frequency_bin_centers_hz"]
        values = []
        for tile in waterfall["tiles"]:
            time_s = offset_s + (tile["sample_start"] + tile["sample_stop"]) / (
                2 * path.binding.sample_rate_hz
            )
            powers = tile["receiver_power_dbfs"][receiver_index]
            for frequency, power in zip(frequencies, powers, strict=True):
                entries.append((path.reference.path_id, time_s, frequency, power))
                values.append((frequency, power))
        lanes.append(_lane_extrema(path.reference.path_id, ("frequency_hz", "power_db"), values))
    selected = _select_by_lane(entries, maximum_points, lambda item: item[0])
    proof = _proof(loaded, paths, StandardViewKindV2.WATERFALL, tuple(lanes))
    frequencies = [item[2] for item in entries]
    powers = [item[3] for item in entries]
    cells = tuple(
        StandardWaterfallCellV2(
            receiver_path_id=lane, time_s=time_s, frequency_hz=frequency, power_db=power
        )
        for lane, time_s, frequency, power in selected
    )
    return StandardPlotViewV2(
        session_id=loaded.snapshot.session_id,
        subject_id=subject.subject_id,
        view_kind=StandardViewKindV2.WATERFALL,
        state=StandardViewStateV2.AVAILABLE,
        time_domain=_time_domain(paths),
        receiver_path_ids=tuple(path.reference.path_id for path in paths),
        horizontal_axis=StandardAxisBoundsV2(
            axis_id="frequency_hz",
            label="Baseband frequency",
            unit="Hz",
            full_source_min=min(frequencies),
            full_source_max=max(frequencies),
        ),
        vertical_axis=_time_axis(paths),
        color_axis=StandardAxisBoundsV2(
            axis_id="power_db",
            label="Power",
            unit="dB",
            full_source_min=min(powers),
            full_source_max=max(powers),
        ),
        source_extrema=proof,
        source_point_count=proof.source_point_count,
        returned_point_count=len(cells),
        truncated=proof.source_point_count > len(cells),
        waterfall_cells=cells,
        reason="Frequency-horizontal/time-vertical waterfall tiles",
    )


def _cfo_view(
    loaded: _Projection,
    subject: StandardSubjectSummaryV2,
    paths: tuple[_PathSource, ...],
    maximum_points: int,
) -> StandardPlotViewV2:
    observations: list[StandardCfoObservationV2] = []
    curves: list[StandardTrajectoryCurveV2] = []
    lane_values: dict[str, list[float]] = defaultdict(list)
    for path in paths:
        lane = path.reference.path_id
        offset_s = _path_time_offset_s(path, paths)
        for index, item in enumerate(path.document["pilot_scan"]["detections"]):
            score = next((score for score in item["scores"] if score["method"] == "glrt64"), None)
            if score is None:
                continue
            observations.append(
                StandardCfoObservationV2(
                    observation_id=f"obs:{lane}:{index}",
                    receiver_path_id=lane,
                    algorithm="glrt64",
                    time_s=offset_s + item["time_s"],
                    baseband_cfo_hz=score["tracking_cfo_hz"],
                    glrt64_response=score["exact_score"],
                )
            )
            lane_values[lane].append(score["tracking_cfo_hz"])
        for item in path.document["trajectory_table"]["trajectories"]:
            count = 17
            local_times = tuple(
                item["start_s"] + (item["end_s"] - item["start_s"]) * index / (count - 1)
                for index in range(count)
            )
            values = tuple(
                _polynomial(item["coefficients_hz"], time_s - item["reference_time_s"])
                for time_s in local_times
            )
            times = tuple(offset_s + time_s for time_s in local_times)
            lane_values[lane].extend(values)
            curves.append(
                StandardTrajectoryCurveV2(
                    trajectory_id=item["trajectory_id"],
                    receiver_path_id=lane,
                    degree=item["polynomial_degree"],
                    selected_for_correction=item["selected_for_correction"],
                    points=tuple(
                        StandardSeriesPointV2(time_s=time_s, value=value)
                        for time_s, value in zip(times, values, strict=True)
                    ),
                )
            )
    flattened = [
        ("observation", item.receiver_path_id, index, -1, item.time_s, item.baseband_cfo_hz)
        for index, item in enumerate(observations)
    ] + [
        ("curve", curve.receiver_path_id, curve_index, point_index, point.time_s, point.value)
        for curve_index, curve in enumerate(curves)
        for point_index, point in enumerate(curve.points)
    ]
    selected = _select_by_lane(flattened, maximum_points, lambda item: item[1])
    observation_ids = {item[2] for item in selected if item[0] == "observation"}
    curve_ids = {(item[2], item[3]) for item in selected if item[0] == "curve"}
    bounded_observations = tuple(
        item for index, item in enumerate(observations) if index in observation_ids
    )
    bounded_curves = tuple(
        curve.model_copy(
            update={
                "points": tuple(
                    point
                    for point_index, point in enumerate(curve.points)
                    if (curve_index, point_index) in curve_ids
                )
            }
        )
        for curve_index, curve in enumerate(curves)
        if any(index == curve_index for index, _ in curve_ids)
    )
    lanes = tuple(
        _lane_extrema(
            path.reference.path_id, ("frequency_hz",), lane_values[path.reference.path_id]
        )
        for path in paths
    )
    proof = _proof(loaded, paths, StandardViewKindV2.CFO_TRAJECTORY, lanes)
    returned = len(bounded_observations) + sum(len(item.points) for item in bounded_curves)
    all_values = [value for values in lane_values.values() for value in values]
    return StandardPlotViewV2(
        session_id=loaded.snapshot.session_id,
        subject_id=subject.subject_id,
        view_kind=StandardViewKindV2.CFO_TRAJECTORY,
        state=StandardViewStateV2.AVAILABLE,
        time_domain=_time_domain(paths),
        receiver_path_ids=tuple(path.reference.path_id for path in paths),
        horizontal_axis=_time_axis(paths),
        vertical_axis=StandardAxisBoundsV2(
            axis_id="frequency_hz",
            label="Baseband CFO",
            unit="Hz",
            full_source_min=min(all_values),
            full_source_max=max(all_values),
        ),
        source_extrema=proof,
        source_point_count=proof.source_point_count,
        returned_point_count=returned,
        truncated=proof.source_point_count > returned,
        cfo_observations=bounded_observations,
        trajectory_curves=bounded_curves,
        reason="GLRT64 CFO observations with fitted candidate trajectories",
    )


def _proof(
    loaded: _Projection,
    paths: tuple[_PathSource, ...],
    kind: StandardViewKindV2,
    lanes: tuple[StandardLaneSourceExtremaV2, ...],
) -> StandardSourceExtremaProofV2:
    content = canonical_digest(
        {"view_kind": kind.value, "products": [item.product.digest for item in paths]}
    )
    return standard_source_extrema_from_lanes_v2(
        source_artifact_digest=loaded.manifest_digest,
        source_content_digest=_digest(content),
        lanes=lanes,
    )


def _lane_extrema(
    path_id: str, axes: tuple[StandardSourceAxisIdV2, ...], values: Iterable[Any]
) -> StandardLaneSourceExtremaV2:
    rows = list(values)
    if not rows:
        raise StandardPresentationUnavailable("Standard view has an empty receiver-path lane")
    columns: tuple[list[Any], ...]
    if len(axes) == 1:
        columns = (rows,)
    else:
        columns = tuple([row[index] for row in rows] for index in range(len(axes)))
    return StandardLaneSourceExtremaV2(
        receiver_path_id=path_id,
        source_point_count=len(rows),
        axes=tuple(
            StandardSourceAxisExtremaV2(
                axis_id=axis, source_min=min(column), source_max=max(column)
            )
            for axis, column in zip(axes, columns, strict=True)
        ),
    )


def _select_by_lane(items: list[Any], maximum: int, lane) -> list[Any]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for item in items:
        grouped[lane(item)].append(item)
    if maximum < len(grouped):
        raise ValueError("maximum_points does not cover every source-backed lane")
    selected = [values[0] for values in grouped.values()]
    remaining = maximum - len(selected)
    candidates = [item for values in grouped.values() for item in values[1:]]
    if remaining and candidates:
        if len(candidates) <= remaining:
            selected.extend(candidates)
        else:
            selected.extend(
                candidates[round(index * (len(candidates) - 1) / (remaining - 1))]
                for index in range(remaining)
            ) if remaining > 1 else selected.append(candidates[-1])
    positions = {id(item): index for index, item in enumerate(items)}
    return sorted(selected, key=lambda item: positions[id(item)])


def _time_axis(paths: tuple[_PathSource, ...]) -> StandardAxisBoundsV2:
    domain = _time_domain(paths)
    return StandardAxisBoundsV2(
        axis_id="time",
        label="Shared elapsed time",
        unit="s",
        full_source_min=domain.elapsed_start_s,
        full_source_max=domain.elapsed_end_s,
    )


def _path_time_offset_s(path: _PathSource, paths: tuple[_PathSource, ...]) -> float:
    first = min(item.binding.timing.first_estimate_utc_ns for item in paths)
    return (path.binding.timing.first_estimate_utc_ns - first) / 1_000_000_000


def _metric_axis_label(kind: StandardViewKindV2) -> str:
    return {
        StandardViewKindV2.QUALITY: "Quality metrics",
        StandardViewKindV2.POWER: "Power",
        StandardViewKindV2.GLRT64: "GLRT64 detector response",
        StandardViewKindV2.QAM: "Known-pilot QAM metrics",
    }[kind]


def _polynomial(coefficients: list[float], offset_s: float) -> float:
    result = 0.0
    for coefficient in coefficients:
        result = result * offset_s + coefficient
    return result


def _digest(value: str | None) -> str:
    if value is None:
        raise StandardPresentationUnavailable("required digest is absent")
    normalized = value.removeprefix("sha256:")
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise StandardPresentationUnavailable("required digest is invalid")
    return normalized
