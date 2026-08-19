"""Small deterministic Standard-v2 fixture for API and browser development."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from leo.pipeline.scopes import ScopeIdentityV1
from leo.presentation.standard_pipeline import (
    StandardAxisBoundsV2,
    StandardCfoObservationV2,
    StandardComputationDispositionV2,
    StandardMetricSeriesV2,
    StandardPathEvidenceV2,
    StandardPipelineReleaseV2,
    StandardPlotViewV2,
    StandardReceiverPathRefV2,
    StandardReuseSummaryV2,
    StandardSeriesPointV2,
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
    standard_source_extrema_proof_v2,
)
from leo.presentation.standard_repository import FixtureStandardPresentationRepository

_SHA = "0123456789abcdef0123456789abcdef01234567"
_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64
_DIGEST_C = "c" * 64
_SESSION = "T1"


def build_standard_fixture_repository(
    *, source_type: StandardSourceTypeV2 = StandardSourceTypeV2.TEST
) -> FixtureStandardPresentationRepository:
    eligibility = standard_eligibility_v2(
        source_type,
        ("TEST",) if source_type is StandardSourceTypeV2.TEST else (),
        capture_committed=True,
        capture_healthy=True,
    )
    release = StandardPipelineReleaseV2(
        authoritative_pipeline_release_id=_SHA,
        source_revision=_SHA,
        display_version="2.0.0",
        graph_digest=_DIGEST_A,
        configuration_digest=_DIGEST_B,
        environment_digest=_DIGEST_C,
    )
    paths = tuple(
        StandardReceiverPathRefV2(
            subject_id=f"path:radio{radio}:rx{receiver}",
            path_id=f"radio{radio}:rx{receiver}",
            radio_id=f"radio{radio}",
            radio_label=f"Radio{radio}",
            receiver_id=receiver,
            receiver_label=f"RX{receiver}",
            scope=ScopeIdentityV1.receiver_path(
                session_id=_SESSION,
                stream_id=f"stream-{radio}",
                receiver_id=receiver,
            ),
            scope_digest=ScopeIdentityV1.receiver_path(
                session_id=_SESSION,
                stream_id=f"stream-{radio}",
                receiver_id=receiver,
            ).canonical_digest.removeprefix("sha256:"),
        )
        for radio in range(2)
        for receiver in range(2)
    )
    path_subjects = tuple(
        _subject(
            subject_id=f"path:{path.path_id}",
            kind=StandardSubjectKindV2.RECEIVER_PATH,
            label=f"{path.radio_label} {path.receiver_label}",
            paths=(path,),
            children=(),
            release=release,
            eligibility=eligibility,
            derived=False,
        )
        for path in paths
    )
    radios = tuple(
        _subject(
            subject_id=f"radio:radio{radio}",
            kind=StandardSubjectKindV2.RADIO,
            label=f"Radio{radio}",
            paths=tuple(path for path in paths if path.radio_id == f"radio{radio}"),
            children=tuple(
                item.subject_id
                for item in path_subjects
                if item.receiver_paths[0].radio_id == f"radio{radio}"
            ),
            release=release,
            eligibility=eligibility,
            derived=True,
        )
        for radio in range(2)
    )
    pair = _subject(
        subject_id="pair:radio0:radio1",
        kind=StandardSubjectKindV2.PAIRED,
        label="Paired Radio0 + Radio1",
        paths=paths,
        children=tuple(item.subject_id for item in radios),
        release=release,
        eligibility=eligibility,
        derived=True,
    )
    hierarchy = StandardSubjectHierarchyV2(
        session_id=_SESSION,
        source_type=source_type,
        eligibility=eligibility,
        generated_at=datetime(2026, 8, 19, 18, 0, tzinfo=UTC),
        rows=(pair, *radios),
    )
    start = datetime(2026, 8, 19, 17, 0, tzinfo=UTC)
    domain = StandardTimeDomainV2(
        absolute_start_utc=start,
        absolute_end_utc=start + timedelta(seconds=60),
        elapsed_end_s=60.0,
        timing_uncertainty_s=0.002,
    )
    details = tuple(
        _detail(
            subject,
            tuple(
                child
                for child in path_subjects
                if child.receiver_paths[0] in subject.receiver_paths
            ),
            domain,
        )
        for subject in (pair, *radios, *path_subjects)
    )
    views = tuple(
        _view(subject.subject_id, kind, domain, subject.receiver_paths)
        for subject in (pair, *radios, *path_subjects)
        for kind in StandardViewKindV2
    )
    return FixtureStandardPresentationRepository(
        hierarchy,
        details,
        views,
        source_bindings={
            (view.subject_id, view.view_kind): (_DIGEST_A, _DIGEST_B) for view in views
        },
    )


def _subject(
    *,
    subject_id: str,
    kind: StandardSubjectKindV2,
    label: str,
    paths: tuple[StandardReceiverPathRefV2, ...],
    children: tuple[str, ...],
    release: StandardPipelineReleaseV2,
    eligibility,
    derived: bool,
) -> StandardSubjectSummaryV2:
    state = (
        StandardSubjectStateV2.COMPLETE
        if eligibility.evidence_only
        else StandardSubjectStateV2.CURRENT
    )
    return StandardSubjectSummaryV2(
        subject_id=subject_id,
        session_id=_SESSION,
        subject_kind=kind,
        label=label,
        derived=derived,
        receiver_paths=paths,
        expected_path_count=len(paths),
        completed_path_count=len(paths),
        child_subject_ids=children,
        state=state,
        ordinary_current=eligibility.promotion_allowed,
        state_reasons=(),
        pipeline_release=release,
        desired_pipeline_release_id=_SHA,
        reuse=StandardReuseSummaryV2(
            computed_stage_count=1,
            reused_stage_count=8 if derived else 3,
            recompute_stage_count=0,
            reused_from_run_ids=("run-source",),
            reason="Exact derivation keys matched immutable child products",
        ),
        eligibility=eligibility,
    )


def _detail(
    subject: StandardSubjectSummaryV2,
    path_subjects: tuple[StandardSubjectSummaryV2, ...],
    domain: StandardTimeDomainV2,
) -> StandardSubjectDetailV2:
    path = subject.receiver_paths[0]
    trajectory = StandardTrajectoryRowV2(
        trajectory_id=f"trajectory:{path.path_id}",
        receiver_path_id=path.path_id,
        algorithm="glrt64",
        degree=2,
        reference_time_s=1.0,
        coefficients_hz=(2.0, -120.0, 253_443.36),
        support_count=27,
        residual_rms_hz=312.5,
        bic=84.1,
        selected_for_correction=True,
        corrected_glrt64_gain=0.142,
        status="selected",
    )
    stages = tuple(
        StandardStageStatusV2(
            stage_key=stage,
            subject_id=subject.subject_id,
            disposition=(
                StandardComputationDispositionV2.COMPUTED
                if stage == "path-presentation"
                else StandardComputationDispositionV2.REUSED
            ),
            runtime_seconds=0.02,
            output_digest=_DIGEST_A,
            reused_from_run_id=None if stage == "path-presentation" else "run-source",
            reason="Rendered for this run" if stage == "path-presentation" else "Exact cache hit",
        )
        for stage in (
            "path-quality",
            "path-pilot-scan",
            "path-trajectory-bank",
            "path-presentation",
        )
    )
    views = tuple(
        StandardViewDescriptorV2(
            view_kind=kind,
            state=StandardViewStateV2.AVAILABLE,
            href=f"/api/v2/recordings/{_SESSION}/standard-subjects/{subject.subject_id}/views/{kind.value}",
            source_point_count=(
                16
                if kind in {StandardViewKindV2.WATERFALL, StandardViewKindV2.CFO_TRAJECTORY}
                else 8 * len(subject.receiver_paths)
                if kind is StandardViewKindV2.POWER
                else 16 * len(subject.receiver_paths)
            ),
            reason="Bounded registered presentation is available",
        )
        for kind in StandardViewKindV2
    )
    return StandardSubjectDetailV2(
        subject=subject,
        time_domain=domain,
        receiver_path_expansions=path_subjects,
        receiver_path_evidence=tuple(
            StandardPathEvidenceV2(
                receiver_path=item,
                coverage_fraction=1.0,
                analyzed_seconds=60.0,
                declared_seconds=60.0,
                quality_state="complete",
                clipped_fraction=0.00001,
                continuity_gap_count=0,
                calibration_state="applicable",
                calibration_id=f"calibration:{item.path_id}",
                calibration_digest=_DIGEST_C,
                frequency_uncertainty_hz=125.0,
                reason="Full path coverage with capture-epoch calibration",
            )
            for item in subject.receiver_paths
        ),
        stage_source_count=len(stages),
        stages=stages,
        stages_truncated=False,
        trajectory_source_count=1,
        trajectories=(trajectory,),
        trajectories_truncated=False,
        views=views,
        limitations=(
            "Candidate evidence only; source identity is unassessed; "
            "no payload recovery is claimed",
            "Cross-radio evidence is score/trajectory-level and is not phase coherent",
        ),
    )


def _view(
    subject_id: str,
    kind: StandardViewKindV2,
    domain: StandardTimeDomainV2,
    paths: tuple[StandardReceiverPathRefV2, ...],
) -> StandardPlotViewV2:
    times = (0.0, 1.513484, 8.0, 20.0, 32.0, 44.0, 52.0, 60.0)
    time_axis = StandardAxisBoundsV2(
        axis_id="time",
        label="Shared elapsed time",
        unit="s",
        full_source_min=domain.elapsed_start_s,
        full_source_max=domain.elapsed_end_s,
    )
    if kind is StandardViewKindV2.WATERFALL:
        cells = tuple(
            StandardWaterfallCellV2(
                receiver_path_id=paths[(time_index * 4 + frequency_index) % len(paths)].path_id,
                time_s=time,
                frequency_hz=250_000.0 + frequency_index * 5_000.0,
                power_db=-70.0 + time_index + frequency_index,
            )
            for time_index, time in enumerate(times[:4])
            for frequency_index in range(4)
        )
        return StandardPlotViewV2(
            session_id=_SESSION,
            subject_id=subject_id,
            view_kind=kind,
            state=StandardViewStateV2.AVAILABLE,
            time_domain=domain,
            receiver_path_ids=tuple(path.path_id for path in paths),
            horizontal_axis=StandardAxisBoundsV2(
                axis_id="frequency_hz",
                label="Baseband frequency",
                unit="Hz",
                full_source_min=250_000.0,
                full_source_max=265_000.0,
            ),
            vertical_axis=time_axis,
            color_axis=StandardAxisBoundsV2(
                axis_id="power_db",
                label="Power",
                unit="dB",
                full_source_min=-70.0,
                full_source_max=-64.0,
            ),
            source_extrema=standard_source_extrema_proof_v2(
                view_kind=kind,
                receiver_path_ids=tuple(path.path_id for path in paths),
                source_artifact_digest=_DIGEST_A,
                source_content_digest=_DIGEST_B,
                waterfall_cells=cells,
            ),
            source_point_count=len(cells),
            returned_point_count=len(cells),
            truncated=False,
            waterfall_cells=cells,
            reason="Frequency-horizontal/time-vertical waterfall tiles",
        )
    if kind is StandardViewKindV2.CFO_TRAJECTORY:
        observations = tuple(
            StandardCfoObservationV2(
                observation_id=f"obs:{index}",
                receiver_path_id=paths[index % len(paths)].path_id,
                algorithm="glrt64",
                time_s=time,
                baseband_cfo_hz=253_443.36 - 120.0 * time + 2.0 * time * time,
                glrt64_response=0.11 + index * 0.01,
                used_by_trajectory_ids=(f"trajectory:{paths[0].path_id}",),
            )
            for index, time in enumerate(times)
        )
        curve_points = tuple(
            StandardSeriesPointV2(
                time_s=time,
                value=253_443.36 - 120.0 * time + 2.0 * time * time,
            )
            for time in times
        )
        curve = StandardTrajectoryCurveV2(
            trajectory_id=f"trajectory:{paths[0].path_id}",
            receiver_path_id=paths[0].path_id,
            degree=2,
            selected_for_correction=True,
            points=curve_points,
        )
        total = len(observations) + len(curve_points)
        frequency_values = tuple(item.baseband_cfo_hz for item in observations) + tuple(
            item.value for item in curve_points
        )
        return StandardPlotViewV2(
            session_id=_SESSION,
            subject_id=subject_id,
            view_kind=kind,
            state=StandardViewStateV2.AVAILABLE,
            time_domain=domain,
            receiver_path_ids=tuple(path.path_id for path in paths),
            horizontal_axis=time_axis,
            vertical_axis=StandardAxisBoundsV2(
                axis_id="frequency_hz",
                label="Baseband CFO",
                unit="Hz",
                full_source_min=min(frequency_values),
                full_source_max=max(frequency_values),
            ),
            source_extrema=standard_source_extrema_proof_v2(
                view_kind=kind,
                receiver_path_ids=tuple(path.path_id for path in paths),
                source_artifact_digest=_DIGEST_A,
                source_content_digest=_DIGEST_B,
                cfo_observations=observations,
                trajectory_curves=(curve,),
            ),
            source_point_count=total,
            returned_point_count=total,
            truncated=False,
            cfo_observations=observations,
            trajectory_curves=(curve,),
            reason="GLRT64 CFO observations with selected quadratic trajectory",
        )
    all_specifications: dict[
        StandardViewKindV2,
        tuple[tuple[str, str, StandardUnitV2, float, float], ...],
    ] = {
        StandardViewKindV2.QUALITY: (
            ("valid", "Valid sample fraction", "fraction", 0.99, 0.0),
            ("clipping", "Clipped sample fraction", "fraction", 0.00001, 0.0),
        ),
        StandardViewKindV2.POWER: (("window", "Window power", "dBFS", -42.0, 1.0),),
        StandardViewKindV2.GLRT64: (
            ("initial", "Initial GLRT64 detector response", "response", 0.08, 0.015),
            (
                "corrected",
                "Trajectory-corrected GLRT64 candidate redetection response",
                "response",
                0.11,
                0.021,
            ),
        ),
        StandardViewKindV2.QAM: (
            ("accuracy", "Known-pilot QAM accuracy", "accuracy", 0.72, 0.02),
            ("evm", "Known-pilot QAM RMS EVM", "EVM", 0.64, -0.015),
        ),
    }
    specifications = all_specifications[kind]
    series = tuple(
        StandardMetricSeriesV2(
            series_id=f"{kind.value}:{metric_id}:{path.path_id}",
            receiver_path_id=path.path_id,
            label=label,
            unit=unit,
            source_point_count=len(times),
            points=tuple(
                StandardSeriesPointV2(
                    time_s=time,
                    value=initial_value + index * increment,
                )
                for index, time in enumerate(times)
            ),
            truncated=False,
            source_min=min(initial_value, initial_value + (len(times) - 1) * increment),
            source_max=max(initial_value, initial_value + (len(times) - 1) * increment),
        )
        for path in paths
        for metric_id, label, unit, initial_value, increment in specifications
    )
    count = sum(len(item.points) for item in series)
    value_min = min(item.source_min for item in series if item.source_min is not None)
    value_max = max(item.source_max for item in series if item.source_max is not None)
    return StandardPlotViewV2(
        session_id=_SESSION,
        subject_id=subject_id,
        view_kind=kind,
        state=StandardViewStateV2.AVAILABLE,
        time_domain=domain,
        receiver_path_ids=tuple(path.path_id for path in paths),
        horizontal_axis=time_axis,
        vertical_axis=StandardAxisBoundsV2(
            axis_id="metric_value",
            label=view_metric_label(kind),
            unit="mixed" if len({item.unit for item in series}) > 1 else series[0].unit,
            full_source_min=value_min,
            full_source_max=value_max,
        ),
        source_extrema=standard_source_extrema_proof_v2(
            view_kind=kind,
            receiver_path_ids=tuple(path.path_id for path in paths),
            source_artifact_digest=_DIGEST_A,
            source_content_digest=_DIGEST_B,
            series=series,
        ),
        source_point_count=count,
        returned_point_count=count,
        truncated=False,
        series=series,
        reason="Bounded aligned-time metric series",
    )


def view_metric_label(kind: StandardViewKindV2) -> str:
    return {
        StandardViewKindV2.QUALITY: "Quality metrics",
        StandardViewKindV2.POWER: "Power",
        StandardViewKindV2.GLRT64: "GLRT64 detector response",
        StandardViewKindV2.QAM: "Known-pilot QAM metrics",
    }[kind]
