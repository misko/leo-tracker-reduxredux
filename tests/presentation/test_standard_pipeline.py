from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from leo.presentation.standard_fixtures import build_standard_fixture_repository
from leo.presentation.standard_pipeline import (
    StandardAxisBoundsV2,
    StandardEligibilityV2,
    StandardPipelineReleaseV2,
    StandardPlotViewV2,
    StandardSourceTypeV2,
    StandardStaleReasonCodeV2,
    StandardStateReasonV2,
    StandardSubjectHierarchyV2,
    StandardSubjectStateV2,
    StandardTimeDomainV2,
    StandardViewKindV2,
    standard_eligibility_v2,
)


def test_dual_radio_fixture_has_exact_top_level_rows_and_receiver_expansions() -> None:
    repository = build_standard_fixture_repository()
    hierarchy = repository.subject_hierarchy("T1")

    assert hierarchy is not None
    assert [(row.subject_kind, row.label) for row in hierarchy.rows] == [
        ("paired", "Paired Radio0 + Radio1"),
        ("radio", "Radio0"),
        ("radio", "Radio1"),
    ]
    assert [len(row.receiver_paths) for row in hierarchy.rows] == [4, 2, 2]
    assert all(row.derived for row in hierarchy.rows)
    assert all(not row.ordinary_current for row in hierarchy.rows)
    assert {row.state for row in hierarchy.rows} == {StandardSubjectStateV2.COMPLETE}
    assert all(row.eligibility.evidence_only for row in hierarchy.rows)
    pair = repository.subject_detail("T1", "pair:radio0:radio1")
    assert pair is not None
    assert [item.label for item in pair.receiver_path_expansions] == [
        "Radio0 RX0",
        "Radio0 RX1",
        "Radio1 RX0",
        "Radio1 RX1",
    ]
    assert {view.view_kind for view in pair.views} == set(StandardViewKindV2)


def test_import_is_ordinary_current_while_test_is_non_current_evidence() -> None:
    imported = build_standard_fixture_repository(
        source_type=StandardSourceTypeV2.IMPORT
    ).subject_hierarchy("T1")
    evidence = build_standard_fixture_repository().subject_hierarchy("T1")
    assert imported is not None and evidence is not None

    assert all(row.state is StandardSubjectStateV2.CURRENT for row in imported.rows)
    assert all(row.ordinary_current for row in imported.rows)
    assert not imported.eligibility.evidence_only
    assert all(row.state is not StandardSubjectStateV2.CURRENT for row in evidence.rows)
    assert all(not row.ordinary_current for row in evidence.rows)

    evidence_row = evidence.rows[0]
    with pytest.raises(ValidationError, match="evidence-only subjects cannot state current"):
        evidence_row.__class__.model_validate(
            evidence_row.model_copy(update={"state": StandardSubjectStateV2.CURRENT}).model_dump()
        )

    incomplete = imported.rows[1]
    with pytest.raises(ValidationError, match="complete expected paths"):
        incomplete.__class__.model_validate(
            incomplete.model_copy(update={"completed_path_count": 1}).model_dump()
        )


def test_release_authority_is_full_exact_git_sha_not_display_alias() -> None:
    valid = {
        "authoritative_pipeline_release_id": "0" * 40,
        "source_revision": "0" * 40,
        "display_version": "2.1.0",
        "graph_digest": "a" * 64,
        "configuration_digest": "b" * 64,
        "environment_digest": "c" * 64,
    }
    release = StandardPipelineReleaseV2.model_validate(valid)
    assert release.display_label == "standard-glrt64-v2 2.1.0"

    with pytest.raises(ValidationError, match="pattern"):
        StandardPipelineReleaseV2.model_validate(
            {**valid, "authoritative_pipeline_release_id": "standard-glrt64-v2"}
        )
    with pytest.raises(ValidationError, match="must equal the exact source revision"):
        StandardPipelineReleaseV2.model_validate({**valid, "source_revision": "1" * 40})


def test_live_import_test_and_excluded_lane_eligibility_is_truthful() -> None:
    readiness = {"capture_committed": True, "capture_healthy": True}
    live = standard_eligibility_v2(StandardSourceTypeV2.LIVE, (), **readiness)
    imported = standard_eligibility_v2(StandardSourceTypeV2.IMPORT, (), **readiness)
    test = standard_eligibility_v2(StandardSourceTypeV2.TEST, ("TEST",), **readiness)
    calibration = standard_eligibility_v2(StandardSourceTypeV2.LIVE, ("CALIBRATION",), **readiness)
    uncommitted = standard_eligibility_v2(
        StandardSourceTypeV2.LIVE,
        (),
        capture_committed=False,
        capture_healthy=True,
    )
    unhealthy = standard_eligibility_v2(
        StandardSourceTypeV2.IMPORT,
        (),
        capture_committed=True,
        capture_healthy=False,
    )

    assert live.automatic_eligible and live.promotion_allowed and not live.evidence_only
    assert imported.automatic_eligible and imported.promotion_allowed
    assert not test.automatic_eligible and test.explicit_eligible
    assert test.evidence_only and not test.promotion_allowed
    assert calibration.exclusion_tags == ("CALIBRATION",)
    assert not calibration.explicit_eligible and not calibration.promotion_allowed
    assert not uncommitted.explicit_eligible and not uncommitted.automatic_eligible
    assert not unhealthy.explicit_eligible and not unhealthy.promotion_allowed
    assert not uncommitted.capture_committed and not unhealthy.capture_healthy
    with pytest.raises(ValidationError, match="fail closed"):
        StandardEligibilityV2.model_validate(
            uncommitted.model_copy(update={"automatic_eligible": True}).model_dump()
        )


def test_stale_state_requires_machine_readable_reason() -> None:
    repository = build_standard_fixture_repository()
    hierarchy = repository.subject_hierarchy("T1")
    assert hierarchy is not None
    current = hierarchy.rows[1]

    with pytest.raises(ValidationError, match="machine-readable stale reason"):
        current.model_copy(update={"state": StandardSubjectStateV2.STALE}).model_validate(
            current.model_copy(
                update={"state": StandardSubjectStateV2.STALE, "state_reasons": ()}
            ).model_dump()
        )

    stale = current.model_copy(
        update={
            "state": StandardSubjectStateV2.STALE,
            "state_reasons": (
                StandardStateReasonV2(
                    code=StandardStaleReasonCodeV2.STAGE_IMPLEMENTATION_CHANGED,
                    message="trajectory implementation changed",
                    affected_stage_keys=("path-trajectory-bank",),
                    affected_subject_ids=(current.subject_id,),
                ),
            ),
        }
    )
    assert stale.state_reasons[0].code == "stage_implementation_changed"


def test_hierarchy_requires_exact_distinct_pair_and_radio_membership() -> None:
    hierarchy = build_standard_fixture_repository().subject_hierarchy("T1")
    assert hierarchy is not None
    pair, radio0, radio1 = hierarchy.rows

    duplicate_radio_path = radio1.model_copy(update={"receiver_paths": radio0.receiver_paths})
    with pytest.raises(ValidationError, match="disjoint receiver-path membership"):
        StandardSubjectHierarchyV2.model_validate(
            hierarchy.model_copy(update={"rows": (pair, radio0, duplicate_radio_path)}).model_dump()
        )

    with pytest.raises(ValidationError, match="ordered radio rows"):
        StandardSubjectHierarchyV2.model_validate(
            hierarchy.model_copy(
                update={
                    "rows": (
                        pair.model_copy(
                            update={"child_subject_ids": tuple(reversed(pair.child_subject_ids))}
                        ),
                        radio0,
                        radio1,
                    )
                }
            ).model_dump()
        )


def test_radio_children_exactly_equal_receiver_path_expansion_subjects() -> None:
    repository = build_standard_fixture_repository()
    detail = repository.subject_detail("T1", "radio:radio0")
    assert detail is not None
    assert detail.subject.child_subject_ids == tuple(
        item.subject_id for item in detail.receiver_path_expansions
    )

    with pytest.raises(ValidationError, match="exactly equal ordered receiver-path expansions"):
        detail.__class__.model_validate(
            detail.model_copy(
                update={
                    "subject": detail.subject.model_copy(
                        update={
                            "child_subject_ids": (
                                "path:radio0:rx1",
                                "path:radio0:rx0",
                            )
                        }
                    )
                }
            ).model_dump()
        )


def test_user_facing_language_remains_candidate_only_and_bounded() -> None:
    with pytest.raises(ValidationError, match="candidate-only"):
        StandardStateReasonV2(message="Confirmed Starlink detection")
    with pytest.raises(ValidationError, match="Starlink-specific"):
        StandardStateReasonV2(message="Likely Starlink candidate")
    with pytest.raises(ValidationError, match="payload evidence"):
        StandardStateReasonV2(message="Candidate payload symbols")
    for unsafe in (
        "Statistically independent trials passed",
        "Independent trial evidence",
        "Phenomenon detected",
        "Target detected",
        "Constellation detection",
    ):
        with pytest.raises(ValidationError):
            StandardStateReasonV2(message=unsafe)

    with pytest.raises(ValidationError, match="at most 32 items"):
        StandardStateReasonV2(
            message="Candidate analysis state",
            affected_stage_keys=tuple(f"stage-{index}" for index in range(33)),
        )


def test_all_views_share_one_time_domain_and_are_deterministically_bounded() -> None:
    repository = build_standard_fixture_repository()
    detail = repository.subject_detail("T1", "pair:radio0:radio1")
    assert detail is not None

    domains = []
    for kind in StandardViewKindV2:
        view = repository.subject_view("T1", "pair:radio0:radio1", kind, maximum_points=5)
        assert view is not None
        domains.append(view.time_domain)
        assert view.returned_point_count <= 5
        assert view.source_point_count >= view.returned_point_count
        assert view.truncated is (view.source_point_count > view.returned_point_count)
        assert tuple(view.receiver_path_ids) == tuple(
            item.path_id for item in detail.subject.receiver_paths
        )
    assert all(domain == detail.time_domain for domain in domains)


def test_paired_plot_rejects_foreign_lane_and_bounded_nested_membership() -> None:
    view = build_standard_fixture_repository().subject_view(
        "T1", "pair:radio0:radio1", StandardViewKindV2.WATERFALL, maximum_points=20
    )
    assert view is not None
    foreign_cell = view.waterfall_cells[0].model_copy(update={"receiver_path_id": "radio9:rx0"})
    with pytest.raises(ValidationError, match="foreign receiver-path lane"):
        StandardPlotViewV2.model_validate(
            view.model_copy(
                update={
                    "waterfall_cells": (foreign_cell, *view.waterfall_cells[1:]),
                }
            ).model_dump()
        )

    cfo_view = build_standard_fixture_repository().subject_view(
        "T1", "pair:radio0:radio1", StandardViewKindV2.CFO_TRAJECTORY, maximum_points=20
    )
    assert cfo_view is not None
    with pytest.raises(ValidationError, match="at most 16 items"):
        cfo_view.cfo_observations[0].__class__.model_validate(
            cfo_view.cfo_observations[0]
            .model_copy(
                update={
                    "used_by_trajectory_ids": tuple(f"trajectory-{index}" for index in range(17))
                }
            )
            .model_dump()
        )


def test_decimation_preserves_authoritative_full_source_axes() -> None:
    repository = build_standard_fixture_repository()
    for kind in (
        StandardViewKindV2.QUALITY,
        StandardViewKindV2.WATERFALL,
        StandardViewKindV2.CFO_TRAJECTORY,
    ):
        full = repository.subject_view("T1", "pair:radio0:radio1", kind, maximum_points=2048)
        bounded = repository.subject_view("T1", "pair:radio0:radio1", kind, maximum_points=4)
        assert full is not None and bounded is not None
        assert bounded.returned_point_count == 4
        assert bounded.source_point_count > bounded.returned_point_count
        assert bounded.truncated is True
        assert bounded.horizontal_axis == full.horizontal_axis
        assert bounded.vertical_axis == full.vertical_axis
        assert bounded.color_axis == full.color_axis
        if bounded.series:
            assert all(
                min(point.value for point in series.points) == series.source_min
                and max(point.value for point in series.points) == series.source_max
                for series in bounded.series
            )
            assert bounded.vertical_axis.full_source_min == min(
                series.source_min for series in bounded.series if series.source_min is not None
            )
            assert bounded.vertical_axis.full_source_max == max(
                series.source_max for series in bounded.series if series.source_max is not None
            )
        if bounded.waterfall_cells:
            assert bounded.horizontal_axis.full_source_min == min(
                item.frequency_hz for item in bounded.waterfall_cells
            )
            assert bounded.horizontal_axis.full_source_max == max(
                item.frequency_hz for item in bounded.waterfall_cells
            )
            assert bounded.color_axis is not None
            assert bounded.color_axis.full_source_min == min(
                item.power_db for item in bounded.waterfall_cells
            )
            assert bounded.color_axis.full_source_max == max(
                item.power_db for item in bounded.waterfall_cells
            )
        if bounded.cfo_observations or bounded.trajectory_curves:
            frequencies = [item.baseband_cfo_hz for item in bounded.cfo_observations] + [
                point.value for curve in bounded.trajectory_curves for point in curve.points
            ]
            assert bounded.vertical_axis.full_source_min == min(frequencies)
            assert bounded.vertical_axis.full_source_max == max(frequencies)


def test_bounded_contract_rejects_decimation_that_drops_full_source_extrema() -> None:
    repository = build_standard_fixture_repository()
    metric = repository.subject_view(
        "T1", "pair:radio0:radio1", StandardViewKindV2.GLRT64, maximum_points=4
    )
    waterfall = repository.subject_view(
        "T1", "pair:radio0:radio1", StandardViewKindV2.WATERFALL, maximum_points=4
    )
    cfo = repository.subject_view(
        "T1", "pair:radio0:radio1", StandardViewKindV2.CFO_TRAJECTORY, maximum_points=4
    )
    assert metric is not None and waterfall is not None and cfo is not None
    assert metric.source_point_count > metric.returned_point_count
    varying_series = next(series for series in metric.series if len(series.points) == 2)
    with pytest.raises(ValidationError, match="retain exact full-source extrema"):
        varying_series.__class__.model_validate(
            varying_series.model_copy(update={"points": varying_series.points[:1]}).model_dump()
        )

    frequency_min = waterfall.horizontal_axis.full_source_min
    missing_frequency_min = tuple(
        item for item in waterfall.waterfall_cells if item.frequency_hz != frequency_min
    )
    with pytest.raises(ValidationError, match="retain exact full-source frequency extrema"):
        StandardPlotViewV2.model_validate(
            waterfall.model_copy(
                update={
                    "waterfall_cells": missing_frequency_min,
                    "returned_point_count": len(missing_frequency_min),
                }
            ).model_dump()
        )

    cfo_min = cfo.vertical_axis.full_source_min
    observations = tuple(item for item in cfo.cfo_observations if item.baseband_cfo_hz != cfo_min)
    curves = tuple(
        curve.model_copy(
            update={"points": tuple(point for point in curve.points if point.value != cfo_min)}
        )
        for curve in cfo.trajectory_curves
        if any(point.value != cfo_min for point in curve.points)
    )
    returned = len(observations) + sum(len(curve.points) for curve in curves)
    with pytest.raises(ValidationError, match="retain exact full-source frequency extrema"):
        StandardPlotViewV2.model_validate(
            cfo.model_copy(
                update={
                    "cfo_observations": observations,
                    "trajectory_curves": curves,
                    "returned_point_count": returned,
                }
            ).model_dump()
        )


def test_metric_axis_must_equal_full_source_series_extrema_and_href_is_bounded() -> None:
    view = build_standard_fixture_repository().subject_view(
        "T1", "radio:radio0", StandardViewKindV2.QUALITY, maximum_points=20
    )
    assert view is not None
    with pytest.raises(ValidationError, match="must equal aggregate"):
        StandardPlotViewV2.model_validate(
            view.model_copy(
                update={
                    "vertical_axis": StandardAxisBoundsV2(
                        axis_id="metric_value",
                        label="Quality",
                        unit="fraction",
                        full_source_min=0.1,
                        full_source_max=0.5,
                    )
                }
            ).model_dump()
        )
    detail = build_standard_fixture_repository().subject_detail("T1", "radio:radio0")
    assert detail is not None
    descriptor = detail.views[0]
    with pytest.raises(ValidationError, match="at most 512 characters"):
        descriptor.__class__.model_validate(
            descriptor.model_copy(update={"href": "/api/v2/" + "x" * 505}).model_dump()
        )


def test_time_domain_durations_must_agree_within_typed_uncertainty() -> None:
    start = datetime(2026, 8, 19, tzinfo=UTC)
    accepted = StandardTimeDomainV2(
        absolute_start_utc=start,
        absolute_end_utc=start + timedelta(seconds=1.4),
        elapsed_end_s=1.0,
        timing_uncertainty_s=0.5,
    )
    assert accepted.timing_uncertainty_s == 0.5
    with pytest.raises(ValidationError, match="disagree beyond uncertainty"):
        StandardTimeDomainV2(
            absolute_start_utc=start,
            absolute_end_utc=start + timedelta(seconds=2),
            elapsed_end_s=1.0,
            timing_uncertainty_s=0.5,
        )


def test_plot_rejects_points_outside_declared_shared_time_domain() -> None:
    start = datetime(2026, 8, 19, tzinfo=UTC)
    domain = StandardTimeDomainV2(
        absolute_start_utc=start,
        absolute_end_utc=start + timedelta(seconds=1),
        elapsed_end_s=1,
        timing_uncertainty_s=0,
    )
    view = build_standard_fixture_repository().subject_view(
        "T1", "radio:radio0", StandardViewKindV2.POWER, maximum_points=2048
    )
    assert view is not None
    bad_series = view.series[0].model_copy(
        update={
            "points": (
                view.series[0].points[0].model_copy(update={"time_s": 2.0}),
                *view.series[0].points[1:],
            ),
        }
    )
    with pytest.raises(ValidationError, match="outside the shared subject time domain"):
        StandardPlotViewV2.model_validate(
            view.model_copy(
                update={
                    "time_domain": domain,
                    "horizontal_axis": StandardAxisBoundsV2(
                        axis_id="time",
                        label="Shared elapsed time",
                        unit="s",
                        full_source_min=0.0,
                        full_source_max=1.0,
                    ),
                    "series": (bad_series, *view.series[1:]),
                    "source_point_count": view.source_point_count,
                    "returned_point_count": view.returned_point_count,
                    "truncated": False,
                }
            ).model_dump()
        )
