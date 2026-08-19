from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from leo.presentation.standard_fixtures import build_standard_fixture_repository
from leo.presentation.standard_pipeline import (
    StandardAxisBoundsV2,
    StandardPipelineReleaseV2,
    StandardPlotViewV2,
    StandardSourceTypeV2,
    StandardStaleReasonCodeV2,
    StandardStateReasonV2,
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
    live = standard_eligibility_v2(StandardSourceTypeV2.LIVE, ())
    imported = standard_eligibility_v2(StandardSourceTypeV2.IMPORT, ())
    test = standard_eligibility_v2(StandardSourceTypeV2.TEST, ("TEST",))
    calibration = standard_eligibility_v2(
        StandardSourceTypeV2.LIVE, ("CALIBRATION",)
    )

    assert live.automatic_eligible and live.promotion_allowed and not live.evidence_only
    assert imported.automatic_eligible and imported.promotion_allowed
    assert not test.automatic_eligible and test.explicit_eligible
    assert test.evidence_only and not test.promotion_allowed
    assert calibration.exclusion_tags == ("CALIBRATION",)
    assert not calibration.explicit_eligible and not calibration.promotion_allowed


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


def test_all_views_share_one_time_domain_and_are_deterministically_bounded() -> None:
    repository = build_standard_fixture_repository()
    detail = repository.subject_detail("T1", "pair:radio0:radio1")
    assert detail is not None

    domains = []
    for kind in StandardViewKindV2:
        view = repository.subject_view(
            "T1", "pair:radio0:radio1", kind, maximum_points=5
        )
        assert view is not None
        domains.append(view.time_domain)
        assert view.returned_point_count <= 5
        assert view.source_point_count >= view.returned_point_count
        assert view.truncated is (view.source_point_count > view.returned_point_count)
    assert all(domain == detail.time_domain for domain in domains)


def test_decimation_preserves_authoritative_full_source_axes() -> None:
    repository = build_standard_fixture_repository()
    for kind in (
        StandardViewKindV2.QUALITY,
        StandardViewKindV2.WATERFALL,
        StandardViewKindV2.CFO_TRAJECTORY,
    ):
        full = repository.subject_view(
            "T1", "pair:radio0:radio1", kind, maximum_points=2048
        )
        bounded = repository.subject_view(
            "T1", "pair:radio0:radio1", kind, maximum_points=1
        )
        assert full is not None and bounded is not None
        assert bounded.returned_point_count == 1
        assert bounded.truncated is True
        assert bounded.horizontal_axis == full.horizontal_axis
        assert bounded.vertical_axis == full.vertical_axis
        assert bounded.color_axis == full.color_axis


def test_metric_axis_cannot_omit_full_source_series_extrema() -> None:
    view = build_standard_fixture_repository().subject_view(
        "T1", "radio:radio0", StandardViewKindV2.QUALITY, maximum_points=20
    )
    assert view is not None
    with pytest.raises(ValidationError, match="omits a full-source series extremum"):
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


def test_plot_rejects_points_outside_declared_shared_time_domain() -> None:
    start = datetime(2026, 8, 19, tzinfo=UTC)
    domain = StandardTimeDomainV2(
        absolute_start_utc=start,
        absolute_end_utc=start + timedelta(seconds=1),
        elapsed_end_s=1,
        timing_uncertainty_s=0,
    )
    view = build_standard_fixture_repository().subject_view(
        "T1", "radio:radio0", StandardViewKindV2.POWER, maximum_points=20
    )
    assert view is not None
    bad_series = view.series[0].model_copy(
        update={
            "points": (view.series[0].points[0].model_copy(update={"time_s": 2.0}),),
            "source_point_count": 1,
            "truncated": False,
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
                    "series": (bad_series,),
                    "source_point_count": 1,
                    "returned_point_count": 1,
                    "truncated": False,
                }
            ).model_dump()
        )
