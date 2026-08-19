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
    assert hierarchy.rows[1].child_subject_ids == tuple(
        path.subject_id for path in hierarchy.rows[1].receiver_paths
    )
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
    with pytest.raises(ValidationError, match="exact source/readiness matrix"):
        StandardEligibilityV2.model_validate(
            uncommitted.model_copy(update={"automatic_eligible": True}).model_dump()
        )
    with pytest.raises(ValidationError, match="exact source/readiness matrix"):
        StandardEligibilityV2.model_validate(
            live.model_copy(update={"promotion_allowed": False}).model_dump()
        )
    with pytest.raises(ValidationError, match="exact source/readiness matrix"):
        StandardEligibilityV2.model_validate(
            test.model_copy(update={"explicit_eligible": False}).model_dump()
        )
    with pytest.raises(ValidationError, match="exact source/readiness matrix"):
        StandardEligibilityV2.model_validate(
            imported.model_copy(update={"evidence_only": True}).model_dump()
        )
    with pytest.raises(ValidationError):
        StandardEligibilityV2.model_validate(
            live.model_copy(update={"exclusion_tags": ("UNREVIEWED",)}).model_dump()
        )

    multiple_exclusions = standard_eligibility_v2(
        StandardSourceTypeV2.LIVE,
        ("ACCEPTANCE", "QUALIFICATION"),
        **readiness,
    )
    assert multiple_exclusions.exclusion_tags == ("QUALIFICATION", "ACCEPTANCE")
    for noncanonical in (
        ("ACCEPTANCE", "QUALIFICATION"),
        ("QUALIFICATION", "QUALIFICATION"),
    ):
        with pytest.raises(ValidationError, match="unique and in canonical order"):
            StandardEligibilityV2.model_validate(
                multiple_exclusions.model_copy(
                    update={"exclusion_tags": noncanonical}
                ).model_dump()
            )

    crossed_reasons = (
        (live, test.reason),
        (test, live.reason),
        (uncommitted, unhealthy.reason),
        (multiple_exclusions, calibration.reason),
    )
    for eligibility, crossed_reason in crossed_reasons:
        with pytest.raises(ValidationError, match="controlled truth projection"):
            StandardEligibilityV2.model_validate(
                eligibility.model_copy(update={"reason": crossed_reason}).model_dump()
            )


def test_stale_state_requires_machine_readable_reason() -> None:
    repository = build_standard_fixture_repository()
    hierarchy = repository.subject_hierarchy("T1")
    assert hierarchy is not None
    current = hierarchy.rows[1]

    with pytest.raises(ValidationError, match="machine-readable stale reasons"):
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
                    message="Stage implementation changed",
                    affected_stage_keys=("path-trajectory-bank",),
                    affected_subject_ids=(current.subject_id,),
                ),
            ),
        }
    )
    assert stale.state_reasons[0].code == "stage_implementation_changed"

    imported = build_standard_fixture_repository(
        source_type=StandardSourceTypeV2.IMPORT
    ).subject_hierarchy("T1")
    assert imported is not None
    ordinary_current = imported.rows[1]
    product_unavailable = StandardStateReasonV2(
        code=StandardStaleReasonCodeV2.PRODUCT_UNAVAILABLE,
        message="Product is unavailable",
    )
    with pytest.raises(ValidationError, match="stale-coded reasons belong only to stale"):
        ordinary_current.__class__.model_validate(
            ordinary_current.model_copy(
                update={"state_reasons": (product_unavailable,)}
            ).model_dump()
        )

    with pytest.raises(ValidationError, match="only machine-readable stale reasons"):
        ordinary_current.__class__.model_validate(
            ordinary_current.model_copy(
                update={
                    "state": StandardSubjectStateV2.STALE,
                    "ordinary_current": False,
                    "state_reasons": (
                        product_unavailable,
                        StandardStateReasonV2(message="Candidate analysis state"),
                    ),
                }
            ).model_dump()
        )

    with pytest.raises(ValidationError, match="controlled rendering of its code"):
        StandardStateReasonV2(
            code=StandardStaleReasonCodeV2.STAGE_IMPLEMENTATION_CHANGED,
            message="Candidate analysis state",
        )


def test_hierarchy_requires_exact_distinct_pair_and_radio_membership() -> None:
    hierarchy = build_standard_fixture_repository().subject_hierarchy("T1")
    assert hierarchy is not None
    pair, radio0, radio1 = hierarchy.rows

    duplicate_radio_path = radio1.model_copy(update={"receiver_paths": radio0.receiver_paths})
    with pytest.raises(ValidationError, match="ordered typed receiver-path subjects"):
        StandardSubjectHierarchyV2.model_validate(
            hierarchy.model_copy(update={"rows": (pair, radio0, duplicate_radio_path)}).model_dump()
        )

    with pytest.raises(ValidationError, match="ordered typed receiver-path subjects"):
        radio0.__class__.model_validate(
            radio0.model_copy(
                update={
                    "child_subject_ids": (
                        "path:foreign:rx0",
                        radio0.child_subject_ids[1],
                    )
                }
            ).model_dump()
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

    with pytest.raises(ValidationError, match="ordered typed receiver-path subjects"):
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
    with pytest.raises(ValidationError, match="controlled candidate-evidence"):
        StandardStateReasonV2(message="Confirmed Starlink detection")
    with pytest.raises(ValidationError, match="controlled candidate-evidence"):
        StandardStateReasonV2(message="Likely Starlink candidate")
    with pytest.raises(ValidationError, match="controlled candidate-evidence"):
        StandardStateReasonV2(message="Candidate payload symbols")
    for unsafe in (
        "Statistically independent trials passed",
        "Independent trial evidence",
        "Phenomenon detected",
        "Target detected",
        "Constellation detection",
        "Satellite presence confirmed",
        "Spacecraft identification",
        "Target attribution is likely",
        "An orbital vehicle was verified",
        "The emitter belongs to a named fleet",
    ):
        with pytest.raises(ValidationError):
            StandardStateReasonV2(message=unsafe)

    with pytest.raises(ValidationError, match="controlled receiver/metric vocabulary"):
        StandardAxisBoundsV2(
            axis_id="metric_value",
            label="Satellite present",
            unit="response",
            full_source_min=0,
            full_source_max=1,
        )

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
        assert bounded.source_extrema == full.source_extrema
        assert repository.verify_source_extrema(
            "T1", "pair:radio0:radio1", kind, bounded.source_extrema
        )
        returned_lanes = {
            *[item.receiver_path_id for item in bounded.series],
            *[item.receiver_path_id for item in bounded.waterfall_cells],
            *[item.receiver_path_id for item in bounded.cfo_observations],
            *[item.receiver_path_id for item in bounded.trajectory_curves],
        }
        assert returned_lanes == set(bounded.receiver_path_ids)
        assert bounded.source_extrema.source_artifact_digest
        assert bounded.source_extrema.source_content_digest
        assert len(bounded.source_extrema.canonical_digest) == 64


def test_bounded_contract_rejects_axis_or_summary_tampering_without_source_proof() -> None:
    repository = build_standard_fixture_repository()
    waterfall = repository.subject_view(
        "T1", "pair:radio0:radio1", StandardViewKindV2.WATERFALL, maximum_points=8
    )
    cfo = repository.subject_view(
        "T1", "pair:radio0:radio1", StandardViewKindV2.CFO_TRAJECTORY, maximum_points=8
    )
    assert waterfall is not None and cfo is not None
    with pytest.raises(ValidationError, match="axes must equal the canonical"):
        StandardPlotViewV2.model_validate(
            waterfall.model_copy(
                update={
                    "horizontal_axis": waterfall.horizontal_axis.model_copy(
                        update={"full_source_min": 251_000.0}
                    ),
                }
            ).model_dump()
        )
    with pytest.raises(ValidationError, match="axes must equal the canonical"):
        StandardPlotViewV2.model_validate(
            cfo.model_copy(
                update={
                    "vertical_axis": cfo.vertical_axis.model_copy(
                        update={
                            "full_source_max": cfo.vertical_axis.full_source_max + 1.0
                        }
                    ),
                }
            ).model_dump()
        )
    with pytest.raises(ValidationError, match="canonical digest"):
        cfo.source_extrema.__class__.model_validate(
            cfo.source_extrema.model_copy(
                update={"source_content_digest": "f" * 64}
            ).model_dump()
        )

    full_waterfall = repository.subject_view(
        "T1", "pair:radio0:radio1", StandardViewKindV2.WATERFALL, maximum_points=2048
    )
    assert full_waterfall is not None and full_waterfall.color_axis is not None
    source_maximum = full_waterfall.color_axis.full_source_max
    shrunken_cells = tuple(
        cell for cell in full_waterfall.waterfall_cells if cell.power_db != source_maximum
    )
    assert len(shrunken_cells) < len(full_waterfall.waterfall_cells)
    with pytest.raises(ValidationError, match="axes must equal the canonical"):
        StandardPlotViewV2.model_validate(
            full_waterfall.model_copy(
                update={
                    "color_axis": full_waterfall.color_axis.model_copy(
                        update={
                            "full_source_max": max(cell.power_db for cell in shrunken_cells)
                        }
                    ),
                    "waterfall_cells": shrunken_cells,
                    "returned_point_count": len(shrunken_cells),
                    "truncated": True,
                }
            ).model_dump()
        )


def test_metric_axis_must_equal_canonical_source_proof_and_href_is_bounded() -> None:
    view = build_standard_fixture_repository().subject_view(
        "T1", "radio:radio0", StandardViewKindV2.QUALITY, maximum_points=20
    )
    assert view is not None
    with pytest.raises(ValidationError, match="axes must equal the canonical"):
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
