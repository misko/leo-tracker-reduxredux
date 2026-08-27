from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import pytest

from leo.analysis.catalogue_observability import analyze_candidate_observability
from leo.analysis.research.catalogue_observability_figures import (
    CatalogueObservabilityFigureError,
    render_catalogue_observability_figures,
)
from tests.analysis.test_catalogue_observability import _config, _inputs


def _result():  # type: ignore[no-untyped-def]
    true, wrong = _inputs()
    return analyze_candidate_observability(
        true_field_bank=true,
        wrong_field_banks=wrong,
        config=_config(true, wrong),
    )


def test_renderer_emits_four_provisional_digest_closed_pngs(tmp_path: Path) -> None:
    result = _result()
    receipts = render_catalogue_observability_figures(
        result,
        output_directory=tmp_path,
        arc_label="synthetic-long-arc",
        annotation_catalog_numbers=(10_001, 99_999),
        maximum_pair_curves=4,
    )

    assert tuple(item.figure_kind for item in receipts) == (
        "candidate-count",
        "closest-pairs",
        "tau-envelope",
        "wrong-epoch-alternatives",
    )
    assert all(item.provisional for item in receipts)
    assert all(item.response_free_series_selection for item in receipts)
    assert all(item.annotations_select_series is False for item in receipts)
    assert all(item.identity_claimed is False for item in receipts)
    assert all(item.source_result_digest == result.content_digest for item in receipts)
    assert receipts[0].annotated_catalog_numbers == ()
    assert 10_001 in receipts[2].annotated_catalog_numbers
    assert 99_999 not in receipts[2].annotated_catalog_numbers
    for receipt in receipts:
        path = tmp_path / receipt.file_name
        payload = path.read_bytes()
        assert payload.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(payload) == receipt.byte_size
        assert receipt.sha256.startswith("sha256:")
        assert receipt.content_digest.startswith("sha256:")


def test_rendering_is_byte_deterministic(tmp_path: Path) -> None:
    result = _result()
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = render_catalogue_observability_figures(
        result,
        output_directory=first_dir,
        arc_label="determinism",
        annotation_catalog_numbers=(10_001, 10_003),
        maximum_pair_curves=5,
    )
    second = render_catalogue_observability_figures(
        result,
        output_directory=second_dir,
        arc_label="determinism",
        annotation_catalog_numbers=(10_003, 10_001, 10_001),
        maximum_pair_curves=5,
    )

    assert first == second
    for left, right in zip(first, second, strict=True):
        assert (first_dir / left.file_name).read_bytes() == (
            second_dir / right.file_name
        ).read_bytes()


def test_annotations_cannot_select_pair_or_base_series(tmp_path: Path) -> None:
    result = _result()
    plain = render_catalogue_observability_figures(
        result,
        output_directory=tmp_path / "plain",
        arc_label="annotation-boundary",
        maximum_pair_curves=3,
    )
    annotated = render_catalogue_observability_figures(
        result,
        output_directory=tmp_path / "annotated",
        arc_label="annotation-boundary",
        annotation_catalog_numbers=(10_001, 10_004),
        maximum_pair_curves=3,
    )

    assert tuple(item.plotted_series_ids for item in plain) == tuple(
        item.plotted_series_ids for item in annotated
    )
    assert plain[1].sha256 != annotated[1].sha256
    assert annotated[1].annotations_select_series is False


def test_renderer_rejects_digest_claim_overlay_and_output_poisons(tmp_path: Path) -> None:
    result = _result()
    poisoned = copy.copy(result)
    object.__setattr__(poisoned, "identity_claimed", True)
    with pytest.raises(CatalogueObservabilityFigureError, match="invalid or digest-open"):
        render_catalogue_observability_figures(
            poisoned,
            output_directory=tmp_path / "poisoned",
            arc_label="poisoned",
        )

    missing_overlay = replace(
        result,
        nuisance_geometries=(
            replace(result.nuisance_geometries[0], floor_overlays=()),
            result.nuisance_geometries[1],
        ),
    )
    with pytest.raises(CatalogueObservabilityFigureError, match="invalid or digest-open"):
        render_catalogue_observability_figures(
            missing_overlay,
            output_directory=tmp_path / "missing",
            arc_label="missing",
        )

    output = tmp_path / "exclusive"
    render_catalogue_observability_figures(
        result,
        output_directory=output,
        arc_label="exclusive",
    )
    with pytest.raises(CatalogueObservabilityFigureError, match="already exists"):
        render_catalogue_observability_figures(
            result,
            output_directory=output,
            arc_label="exclusive",
        )

    with pytest.raises(CatalogueObservabilityFigureError, match="arc label"):
        render_catalogue_observability_figures(
            result,
            output_directory=tmp_path / "bad-label",
            arc_label="../escape",
        )
